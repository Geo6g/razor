"""
GrowthPilot AI — Agentic Conversion Engine

Architecture:
  AI proposes  →  Backend validates  →  Tool executes  →  Outcome recorded

The LLM reasons over full context and proposes a structured action.
The backend enforces all merchant policies and safety guardrails.
"""

import os
import json
import re
from dotenv import load_dotenv
import db

load_dotenv()

CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')

# ── Supported action whitelist ────────────────────────────────────────────────
SUPPORTED_ACTIONS = {
    "offer_discount",
    "offer_free_shipping",
    "recommend_cheaper_alternative",
    "recommend_bundle",
    "compare_products",
    "ask_clarifying_question",
    "no_incentive",
    "prepare_checkout"
}

# ── Risk classification ───────────────────────────────────────────────────────
# LOW   → AI can execute automatically (no incentive, comparisons, alternatives, checkout)
# MEDIUM→ Backend policy validation required before execution (free shipping, small incentives)
# HIGH  → Merchant approval required before execution (large discounts, above threshold)

ACTION_BASE_RISK = {
    "no_incentive":                  "LOW",
    "ask_clarifying_question":       "LOW",
    "recommend_cheaper_alternative": "LOW",
    "compare_products":              "LOW",
    "prepare_checkout":              "LOW",
    "recommend_bundle":              "MEDIUM",
    "offer_free_shipping":           "MEDIUM",
    "offer_discount":                "MEDIUM",   # elevated to HIGH based on amount
}


def classify_action_risk(action, proposal, merchant_settings):
    """
    Classify the proposed action into LOW / MEDIUM / HIGH risk.

    HIGH is forced when:
      - action == 'offer_discount' AND the discount % exceeds
        merchant_settings['high_risk_discount_threshold']
      - action == 'offer_discount' AND there is no configured threshold
        (defaults to 15%).

    Returns one of: 'LOW', 'MEDIUM', 'HIGH'
    """
    base = ACTION_BASE_RISK.get(action, "MEDIUM")
    if action == "offer_discount":
        proposed_pct   = (proposal.get('action_params') or {}).get('discount_pct') or \
                          merchant_settings.get('max_discount_pct', 10.0)
        threshold      = merchant_settings.get('high_risk_discount_threshold', 15.0)
        if proposed_pct >= threshold:
            return "HIGH"
        return base   # MEDIUM
    return base

# ── Bundle pairs: complementary products by category ─────────────────────────
BUNDLE_PAIRS = {
    "earbuds":      ["accessories", "smartwatches"],
    "headphones":   ["accessories", "gaming"],
    "speakers":     ["accessories", "smart_home"],
    "smartwatches": ["accessories", "wearables"],
    "gaming":       ["accessories", "headphones"],
    "smart_home":   ["accessories", "speakers"],
    "wearables":    ["smartwatches", "accessories"],
    "accessories":  ["earbuds", "headphones", "gaming", "speakers"]
}

# ── Objective display labels ──────────────────────────────────────────────────
OBJECTIVE_LABELS = {
    "maximize_conversions": "Maximize Conversions",
    "protect_profit":       "Protect Profit",
    "increase_aov":         "Increase Average Order Value",
    "clear_inventory":      "Clear Inventory"
}

# ── Explicit Category-to-Complementary Product Mappings (Upsell & Cross-Sell) ─
COMPLEMENTARY_MAPPINGS = {
    "earbuds": [
        {"type": "protective_case", "keywords": ["case", "silicone", "pouch", "travel", "cover"], "product_id": "prod_acc_04", "name": "FlexShield Silicone Case", "pitch": "protect your earbuds with shock-absorbent liquid silicone against drops and scratches"},
        {"type": "charging_stand",  "keywords": ["charger", "dock", "stand", "magcharge", "wireless"], "product_id": "prod_acc_01", "name": "MagCharge Wireless Stand", "pitch": "enable fast 15W MagSafe wireless docking alongside your phone"},
        {"type": "cleaning_kit",    "keywords": ["clean", "brush", "cleaning", "maintenance"], "product_id": "prod_acc_08", "name": "ScreenMaster 7-in-1 Cleaning Kit", "pitch": "keep sound grilles and charge contacts spotless for optimal acoustic clarity"}
    ],
    "headphones": [
        {"type": "travel_case",    "keywords": ["case", "travel", "eva", "pouch"], "product_id": "prod_acc_12", "name": "CableOrganizer Hard Travel Case", "pitch": "protect your investment with a waterproof shockproof EVA travel shell"},
        {"type": "fast_charger",   "keywords": ["charger", "gan", "adapter"], "product_id": "prod_acc_05", "name": "GaNFast 65W Triple Charger", "pitch": "get ultra-fast dual USB-C charging on the go"},
        {"type": "braided_cable",  "keywords": ["cable", "cord", "wire", "type-c"], "product_id": "prod_acc_03", "name": "UltraLink Braided Cable 2M", "pitch": "have a heavy-duty 100W braided backup connection"}
    ],
    "smartwatches": [
        {"type": "charging_dock",    "keywords": ["dock", "stand", "charger"], "product_id": "prod_acc_01", "name": "MagCharge Wireless Stand", "pitch": "dock your watch and phone together seamlessly on your nightstand"},
        {"type": "screen_protector", "keywords": ["screen", "guard", "glass"], "product_id": "prod_acc_16", "name": "Privacy Glass Screen Protector (2-Pack)", "pitch": "shield the display with 9H diamond hardness scratch resistance"}
    ],
    "speakers": [
        {"type": "travel_case",   "keywords": ["case", "travel", "pouch"], "product_id": "prod_acc_12", "name": "CableOrganizer Hard Travel Case", "pitch": "safeguard your speaker during outdoor travel"},
        {"type": "power_station", "keywords": ["battery", "power", "solar"], "product_id": "prod_acc_02", "name": "PowerVolt 20000mAh Power Bank", "pitch": "power extended 48+ hour playback anywhere"}
    ],
    "gaming": [
        {"type": "desk_mat",     "keywords": ["mat", "pad", "desk", "rgb"], "product_id": "prod_acc_18", "name": "RGB Desk Mat Extra Large (900x400mm)", "pitch": "enhance speed-surface tracking and RGB atmosphere on your desk"},
        {"type": "cleaning_kit", "keywords": ["clean", "brush"], "product_id": "prod_acc_08", "name": "ScreenMaster 7-in-1 Cleaning Kit", "pitch": "keep switches and sensor lenses dust-free"}
    ]
}


def find_complementary_upsell(main_product, user_query=""):
    """
    Evaluates category-aligned complementary products with stock verification,
    margin guard, and expected revenue/profit impact.
    """
    if not main_product:
        return None
    category = main_product.get('category', 'earbuds')
    mappings = COMPLEMENTARY_MAPPINGS.get(category, COMPLEMENTARY_MAPPINGS['earbuds'])

    q_lower = user_query.lower() if user_query else ""
    matched_mapping = None

    if q_lower:
        for m in mappings:
            if any(kw in q_lower for kw in m['keywords']):
                matched_mapping = m
                break

    if not matched_mapping:
        matched_mapping = mappings[0]

    acc_product = db.get_product(matched_mapping['product_id'])

    # Fallback to any available in-stock accessory if specific item is out of stock
    if not acc_product or acc_product.get('stock', 0) <= 0:
        all_acc = [p for p in db.get_products('accessories') if p['stock'] > 0]
        if all_acc:
            acc_product = min(all_acc, key=lambda p: p['price'])
        else:
            return None

    return {
        "main_product": main_product,
        "complementary_product": acc_product,
        "pitch_reason": matched_mapping.get('pitch', 'essential paired accessory'),
        "item_type": matched_mapping.get('type', 'accessory').replace('_', ' ').title(),
        "stock_available": acc_product.get('stock', 0),
        "incremental_revenue": acc_product.get('price', 0),
        "bundle_price": main_product.get('price', 0) + acc_product.get('price', 0)
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Intent Parsing (unchanged core, extended with clarifying_question & upsell)
# ─────────────────────────────────────────────────────────────────────────────

def fallback_parse(message, current_state='idle'):
    msg = message.lower().strip()
    tokens = set(re.findall(r'\b\w+\b', msg))

    confirm_words = {'yes', 'confirm', 'proceed', 'pay', 'correct', 'sure', 'ok', 'yea', 'yeah', 'yep', 'y'}
    if tokens.intersection(confirm_words) or 'lets go' in msg or "let's go" in msg:
        return {"action": "confirm", "query": None, "max_price": None, "quantity": 1, "customer_signal": "ready_to_buy"}

    cancel_words = {'no', 'cancel', 'decline', 'declined', 'reject', 'rejected', 'stop', 'abort', 'nope', 'dont', 'n', 'nevermind', 'pass', 'skip'}
    if tokens.intersection(cancel_words) or 'never mind' in msg or "don't" in msg or "not interested" in msg or "no thanks" in msg:
        return {"action": "cancel", "query": None, "max_price": None, "quantity": 1, "customer_signal": "general"}

    customer_signal = "general"
    compare_words = {'compare', 'vs', 'versus', 'difference', 'better', 'recommend'}
    price_words = {'expensive', 'costly', 'cost', 'price', 'discount', 'coupon', 'cheaper', 'reduction', 'off', 'negotiate', 'deal', 'offer'}
    buy_words   = {'buy', 'order', 'purchase', 'checkout', 'pay now'}
    feat_words  = {'battery', 'warranty', 'waterproof', 'specs', 'feature', 'color', 'size', 'compatible', 'anc', 'noise'}
    upsell_words = {'accessory', 'accessories', 'case', 'cover', 'charger', 'stand', 'cable', 'cleaning', 'attachment', 'add-on', 'addon', 'bundle', 'cross-sell', 'upsell', 'protect', 'pair'}

    if tokens.intersection(upsell_words) or 'what accessories' in msg or 'protective case' in msg or 'charging accessory' in msg or 'pair with' in msg:
        customer_signal = "upsell_opportunity"
    elif tokens.intersection(compare_words) or 'which one' in msg or 'side by side' in msg:
        customer_signal = "comparison"
    elif tokens.intersection(price_words) or "too high" in msg or "too much" in msg or "over budget" in msg:
        customer_signal = "price_objection"
    elif tokens.intersection(buy_words) or 'i want to buy' in msg or "let's order" in msg:
        customer_signal = "ready_to_buy"
    elif tokens.intersection(feat_words):
        customer_signal = "feature_inquiry"

    quantity = 1
    # Match explicit quantity phrases like '2 items', '3 pcs', '2 units', '5x'
    qm = re.search(r'\b(\d+)\s*(?:items?|pcs?|units?|pieces?|x\b)', msg)
    if qm:
        quantity = int(qm.group(1))
    else:
        # Match standalone number only if not followed by % or percent or currency
        m = re.search(r'(?<![₹\d])\b([1-9]\d?)\b(?!\s*(?:%|percent|k\b|rs|inr|rupees))', msg)
        if m:
            v = int(m.group(1))
            # Don't treat common discount numbers (10, 15, 20, 25, 30, 50) as quantity unless explicit unit words are used
            if v <= 5 and not re.search(rf'\b{v}\s*%', msg):
                quantity = v

    max_price = None
    pm = re.search(r'(?:under|below|max|budget|within|price)\s*(?:rs\.?|inr|rupees|₹)?\s*(\d+(?:\.\d+)?)', msg)
    if pm:
        max_price = float(pm.group(1))
        if customer_signal == "general":
            customer_signal = "budget_constraint"

    clean = msg
    for pat in [r'\b(buy|order|search|find|get|want to buy|want|need|show me|show|look for|purchase|tell me about|compare|accessories|accessory)\b',
                r'\b(under|below|max|budget|within|price)\s*(?:rs\.?|inr|rupees|₹)?\s*\d+(?:\.\d+)?\b',
                r'\b\d+\s*%\s*(?:off|discount)?\b',
                r'\b(items|pcs|units|pieces|of)\b']:
        clean = re.sub(pat, '', clean)
    clean = clean.strip()

    action = "search" if len(clean) > 1 else "unclear"
    if customer_signal == "upsell_opportunity":
        action = "upsell"
    elif customer_signal == "comparison":
        action = "compare"
    elif customer_signal == "ready_to_buy":
        action = "buy"

    return {"action": action, "query": clean if clean else None,
            "max_price": max_price, "quantity": quantity, "customer_signal": customer_signal}


def parse_intent(session_id, message, current_state='idle'):
    msg_lower = message.lower().strip()

    if msg_lower in ['yes', 'confirm', 'y', 'proceed', 'lets go', "let's go", 'buy'] and current_state == 'awaiting_confirmation':
        intent = {"action": "confirm", "query": None, "max_price": None, "quantity": 1, "customer_signal": "ready_to_buy"}
        db.log_audit(session_id, "intent_parsed", "Fast-path confirmation.", {"intent": intent})
        return intent

    if msg_lower in ['no', 'cancel', 'decline', 'declined', 'reject', 'rejected', 'n', 'stop', 'abort', 'nope', 'no thanks', 'not now', 'pass', 'skip'] and current_state == 'awaiting_confirmation':
        intent = {"action": "cancel", "query": None, "max_price": None, "quantity": 1, "customer_signal": "general"}
        db.log_audit(session_id, "intent_parsed", "Fast-path cancellation.", {"intent": intent})
        return intent

    if CLAUDE_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            system = (
                "You are an intent parser for a commerce agent. Analyze the user message and return ONLY valid JSON.\n\n"
                "Schema:\n"
                '{"action":"search"|"confirm"|"cancel"|"unclear","query":string|null,'
                '"max_price":number|null,"quantity":integer,"customer_signal":'
                '"price_objection"|"budget_constraint"|"ready_to_buy"|"feature_inquiry"|"general"}\n\n'
                "Definitions:\n"
                "- price_objection: 'too expensive', 'discount?', 'cheaper option'\n"
                "- budget_constraint: 'under 2000', 'within 3000'\n"
                "- ready_to_buy: 'buy this', 'checkout', 'i want it'\n"
                "- feature_inquiry: 'battery life?', 'waterproof?'\n"
                "- general: browsing, greeting, vague"
            )
            resp = client.messages.create(
                model="claude-3-5-sonnet-20241022", max_tokens=200, temperature=0.0,
                system=system,
                messages=[{"role": "user", "content": f'Parse: "{message}" (State: {current_state})'}]
            )
            text = resp.content[0].text.strip()
            m = re.search(r'(\{.*\})', text, re.DOTALL)
            intent = json.loads(m.group(1) if m else text)
            if all(k in intent for k in ('action', 'query', 'max_price', 'quantity', 'customer_signal')):
                db.log_audit(session_id, "intent_parsed", "Parsed via Claude API.", {"intent": intent})
                return intent
        except Exception as e:
            db.log_audit(session_id, "intent_parsed_warning", f"Claude parse failed: {e}. Using fallback.")

    intent = fallback_parse(message, current_state)
    db.log_audit(session_id, "intent_parsed", "Parsed via keyword fallback.", {"intent": intent})
    return intent


# ─────────────────────────────────────────────────────────────────────────────
# 2. Product Matching (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def match_product(session_id, query, max_price=None, quantity=1):
    if not query:
        return None, "No search term provided."

    products = db.get_products()
    query_tokens = query.lower().split()
    scored = []

    for p in products:
        score = 0
        nl, dl, cl = p['name'].lower(), p['description'].lower(), p['category'].lower()
        if query.lower() == nl:   score += 150
        elif query.lower() in nl: score += 50
        for t in query_tokens:
            if t in nl: score += 20
            if t in cl: score += 10
            if t in dl: score += 3
        if max_price is not None and p['price'] > max_price:
            score = -1
        if score > 0:
            scored.append((p, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    payload = {"query": query, "max_price": max_price, "quantity": quantity, "candidates": len(scored)}

    if not scored:
        db.log_audit(session_id, "search_match_failed", f"No match for '{query}'.", payload)
        return None, "No matching products found."

    best = scored[0][0]
    payload["matched_product"] = best

    if best['stock'] < quantity:
        db.log_audit(session_id, "search_match_failed", f"'{best['name']}' out of stock.", payload)
        return best, f"'{best['name']}' is out of stock ({best['stock']} remaining)."

    db.log_audit(session_id, "search_match_success", f"Matched '{best['name']}' (score {scored[0][1]}).", payload)
    return best, "Success"


def match_top_products(session_id, query, max_price=None, limit=3):
    """Return top-N matching products for comparison or recommendation display."""
    if not query:
        return []
    products = db.get_products()
    query_tokens = query.lower().split()
    scored = []
    for p in products:
        score = 0
        nl, dl, cl = p['name'].lower(), p['description'].lower(), p['category'].lower()
        if query.lower() in nl: score += 50
        for t in query_tokens:
            if t in nl: score += 20
            if t in cl: score += 10
            if t in dl: score += 3
        if max_price is not None and p['price'] > max_price:
            score = -1
        if score > 0:
            scored.append((p, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:limit]]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Multi-step Planning: missing info detection
# ─────────────────────────────────────────────────────────────────────────────

# Categories that often need budget clarification
HIGH_VARIANCE_CATEGORIES = {'smartwatches', 'headphones', 'speakers'}

def check_missing_info(intent, matched_products):
    """
    Lightweight planning step. Returns a clarifying question if key info is missing.
    Returns None if sufficient info is available to proceed.
    """
    signal = intent.get('customer_signal', 'general')
    query  = intent.get('query', '') or ''
    budget = intent.get('max_price')

    # If already in buy/objection flow, don't redirect to clarification
    if signal in ('ready_to_buy', 'price_objection') or intent.get('action') in ('confirm', 'cancel'):
        return None

    # If query is very short/generic and category is ambiguous
    if len(query.split()) <= 1 and not matched_products:
        return "What type of product are you looking for, and do you have a budget in mind?"

    # If query hits a high-variance category with no budget and many options
    if matched_products and not budget:
        cats = {p['category'] for p in matched_products[:3]}
        if cats.intersection(HIGH_VARIANCE_CATEGORIES) and len(matched_products) >= 3:
            return f"I found several options. What's your approximate budget so I can narrow it down for you?"

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bundle finding
# ─────────────────────────────────────────────────────────────────────────────

def find_bundle_partner(product):
    """Find a complementary in-stock product to pair with the given one."""
    target_categories = BUNDLE_PAIRS.get(product['category'], ['accessories'])
    all_products = db.get_products()
    candidates = [
        p for p in all_products
        if p['category'] in target_categories
        and p['id'] != product['id']
        and p['stock'] > 0
        and p['price'] <= product['price'] * 0.6  # partner should be reasonably cheaper
    ]
    if not candidates:
        return None
    # Pick cheapest qualifying partner
    return min(candidates, key=lambda p: p['price'])


# ─────────────────────────────────────────────────────────────────────────────
# 5. Core: AI Strategy Proposer (Claude with full context)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """You are GrowthPilot, an autonomous commerce agent that helps merchants convert customer interest into profitable transactions.

Your primary goal is to optimize for the active merchant objective while respecting all backend-enforced policies.

OBJECTIVE-SPECIFIC BEHAVIORAL MANDATES:
1. When Active Objective is 'Protect Profit' (protect_profit):
   - For price objections: NEVER propose percentage discounts. Propose 'recommend_cheaper_alternative', 'offer_free_shipping' (if margin permits), or 'no_incentive'.
   - Core Goal: Preserve margin percentage and unit economics. Do not erode margins.
2. When Active Objective is 'Maximize Conversions' (maximize_conversions):
   - For price objections: Propose 'offer_discount' (up to max allowed discount) to eliminate price resistance and close the checkout immediately.
   - Core Goal: Maximize conversion rate and completed orders.
3. When Active Objective is 'Increase Average Order Value' (increase_aov):
   - For price objections and inquiries: Propose 'recommend_bundle' pairing the main product with a complementary accessory or partner product.
   - Core Goal: Elevate basket size and revenue per transaction.

General Guidelines:
1. Understand customer intent and state from conversation.
2. Use provided product data only — never invent facts or prices.
3. Select the single most appropriate action from the supported action list matching the merchant objective.
4. Return ONLY valid JSON matching the schema below.

Supported actions:
- offer_discount: Propose a percentage discount (Maximize Conversions)
- offer_free_shipping: Waive the shipping fee (Protect Profit / Moderate Incentive)
- recommend_cheaper_alternative: Suggest a lower-priced product in the same category (Protect Profit)
- recommend_bundle: Suggest main product + complementary item (Increase AOV)
- compare_products: Show two products side-by-side
- ask_clarifying_question: Request missing information
- no_incentive: Proceed without incentive (Protect Profit / High intent)
- prepare_checkout: Customer is ready; initiate order flow

Output schema:
{
  "customer_state": string,
  "recommended_action": string,
  "confidence": float,
  "reasoning": string,
  "expected_outcome": string,
  "action_params": {
    "discount_pct": number|null,
    "customer_message": string
  }
}"""


def propose_strategy(session_id, product, signal, quantity,
                     conversation_history, merchant_settings,
                     customer_memory, strategy_stats, user_message=""):
    """
    Call Claude with full structured context to propose an agentic strategy.
    Falls back to heuristic if Claude unavailable.

    Returns: dict with recommended_action, confidence, reasoning, customer_state,
             expected_outcome, action_params
    """
    objective_label = OBJECTIVE_LABELS.get(merchant_settings.get('objective', 'protect_profit'),
                                           'Protect Profit')
    margin = product.get('profit_margin', 0)
    max_disc = merchant_settings.get('max_discount_pct', 20.0)
    min_margin = merchant_settings.get('min_margin', 400.0)
    shipping_cost = merchant_settings.get('shipping_cost', 100.0)

    # Format strategy stats for context
    stats_lines = []
    for strategy, stat in (strategy_stats or {}).items():
        stats_lines.append(
            f"  {strategy}: {stat['conversion_rate']}% conversion "
            f"({stat['converted']}/{stat['total']} sessions), avg revenue Rs.{stat['avg_revenue']}"
        )
    stats_text = "\n".join(stats_lines) if stats_lines else "  No historical data yet."

    # Format recent conversation
    history_lines = []
    for msg in (conversation_history or [])[-6:]:
        role = "Customer" if msg['sender'] == 'user' else "GrowthPilot"
        history_lines.append(f"  {role}: {msg['message'][:150]}")
    history_text = "\n".join(history_lines) if history_lines else "  (new conversation)"

    # Customer memory context
    mem_lines = []
    if customer_memory.get('last_product_name'):
        mem_lines.append(f"  Previously viewed: {customer_memory['last_product_name']}")
    if customer_memory.get('last_objection'):
        mem_lines.append(f"  Previous objection: {customer_memory['last_objection']}")
    if customer_memory.get('incentive_offered') and customer_memory['incentive_offered'] != 'none':
        mem_lines.append(f"  Incentive already offered this session: {customer_memory['incentive_offered']}")
    if customer_memory.get('converted'):
        mem_lines.append("  Customer has previously converted (returning buyer).")
    mem_text = "\n".join(mem_lines) if mem_lines else "  No prior session data."

    context_prompt = f"""## Customer Context
- Detected Signal: {signal}
- Purchase Quantity: {quantity}
- Latest Customer Message: {user_message}

## Recent Conversation
{history_text}

## Product Under Evaluation
- ID: {product['id']}
- Name: {product['name']}
- Category: {product['category']}
- Price: Rs.{product['price']:,.2f}
- Description: {product['description'][:120]}

## Merchant Configuration
- Active Objective: {objective_label}
- Max Allowed Discount: {max_disc}%
- Minimum Acceptable Margin After Incentive: Rs.{min_margin:,.2f}
- Shipping Cost to Waive: Rs.{shipping_cost:,.2f}

## Strategy Performance (last 30 days — Outcome-Informed Context)
{stats_text}

## Customer Memory
{mem_text}

Choose the single best action for this exact situation. Follow the Active Objective ({objective_label}) strictly."""

    if CLAUDE_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            resp = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=600,
                temperature=0.3,
                system=AGENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": context_prompt}]
            )
            text = resp.content[0].text.strip()
            m = re.search(r'(\{.*\})', text, re.DOTALL)
            proposal = json.loads(m.group(1) if m else text)

            # Validate proposal schema
            required = {'recommended_action', 'confidence', 'reasoning', 'customer_state', 'expected_outcome', 'action_params'}
            if not all(k in proposal for k in required):
                raise ValueError("Incomplete proposal schema from Claude.")

            # Enforce whitelist
            if proposal['recommended_action'] not in SUPPORTED_ACTIONS:
                raise ValueError(f"Unsupported action: {proposal['recommended_action']}")

            db.log_audit(session_id, "agent_decision_claude",
                         f"Claude proposed '{proposal['recommended_action']}' (conf={proposal['confidence']:.2f}). {proposal['reasoning']}",
                         {"proposal": proposal})
            return proposal

        except Exception as e:
            db.log_audit(session_id, "agent_decision_warning",
                         f"Claude proposal failed: {e}. Falling back to heuristic.", {})

    # ── Heuristic fallback (objective-aware) ─────────────────────────────────
    return _heuristic_propose(session_id, product, signal, merchant_settings,
                               customer_memory, strategy_stats, user_message=user_message)


def _heuristic_propose(session_id, product, signal, merchant_settings, customer_memory, strategy_stats, user_message=""):
    """Objective-aware deterministic decision engine directly driven by merchant objective and customer input."""
    margin      = product['profit_margin']
    objective   = merchant_settings.get('objective', 'protect_profit')
    max_disc    = float(merchant_settings.get('max_discount_pct', 20.0))
    min_margin  = float(merchant_settings.get('min_margin', 400.0))
    shipping    = float(merchant_settings.get('shipping_cost', 100.0))
    threshold   = float(merchant_settings.get('high_risk_discount_threshold', 10.0))
    inc_offered = customer_memory.get('incentive_offered', 'none')

    # Check for explicit customer discount percentage requests (e.g., "Can I get a 15% discount?" or "25% off")
    explicit_discount = None
    if user_message:
        dm = re.search(r'(\d+)\s*%\s*(?:off|discount)?', user_message.lower())
        if dm:
            explicit_discount = float(dm.group(1))

    action = "no_incentive"
    confidence = 0.7
    reasoning = "No objection detected. Standard catalog pricing applied."
    customer_message = f"I found a great match: **{product['name']}** at Rs.{product['price']:,.0f}. Would you like to proceed?"

    # Handle explicit discount request
    if explicit_discount is not None:
        action = "offer_discount"
        confidence = 0.92
        reasoning = f"Customer explicitly requested a {explicit_discount:.0f}% discount. Evaluating against hard policy boundaries and approval threshold."
        customer_message = f"Evaluating your request for a {explicit_discount:.0f}% discount on **{product['name']}**."

    elif signal in ('price_objection', 'budget_constraint'):
        # Don't offer another incentive if already used one this session
        if inc_offered != 'none':
            action = "recommend_cheaper_alternative"
            confidence = 0.85
            reasoning = "Incentive already offered in this session. Suggesting cheaper alternative to protect margin."
            customer_message = f"I understand the price concern. Let me find you a more affordable option in the same category."

        # ── 1. PROTECT PROFIT: Prefer Cheaper Alternative / Free Shipping / Minimal Incentive
        elif objective == 'protect_profit':
            category_products = [p for p in db.get_products(product['category']) if p['id'] != product['id'] and p['price'] < product['price'] and p['stock'] > 0]
            if category_products:
                cheapest = min(category_products, key=lambda p: p['price'])
                action = "recommend_cheaper_alternative"
                confidence = 0.88
                reasoning = "Objective is Protect Profit. Preserves margin by suggesting a cheaper alternative instead of discounting."
                customer_message = f"Since price is a concern, I recommend **{cheapest['name']}** at Rs.{cheapest['price']:,.0f} — it covers 90% of the same features at a better price point."
            elif margin > min_margin + shipping:
                action = "offer_free_shipping"
                confidence = 0.80
                reasoning = "Objective is Protect Profit. Waiving shipping fee (minimal incentive) to protect core product margin."
                customer_message = f"I can waive the Rs.{shipping:.0f} shipping fee on **{product['name']}** to help with your budget."
            else:
                action = "no_incentive"
                confidence = 0.70
                reasoning = "Objective is Protect Profit. Preserving margin without concessions by reinforcing product quality and value."
                customer_message = f"**{product['name']}** at Rs.{product['price']:,.0f} delivers premium performance for its tier. Ready to proceed?"

        # ── 2. MAXIMIZE CONVERSIONS: Prefer Stronger Valid Incentives / Safe Discounts
        elif objective == 'maximize_conversions':
            safe_disc = min(max_disc, threshold, 10.0)
            if margin > min_margin + (product['price'] * safe_disc / 100):
                action = "offer_discount"
                confidence = 0.90
                disc_val = product['price'] * (safe_disc / 100)
                final_p = product['price'] - disc_val
                reasoning = f"Objective is Maximize Conversions. Offering an auto-approved {safe_disc:.0f}% discount within policy limits to eliminate price resistance."
                customer_message = f"Good news! To help you complete your order today, I can apply a special {safe_disc:.0f}% discount on **{product['name']}**. Your price is now Rs.{final_p:,.0f}."
            else:
                action = "offer_free_shipping"
                confidence = 0.80
                reasoning = "Objective is Maximize Conversions. Margin bounds prevent full discount; offering free shipping as conversion lever."
                customer_message = f"I can waive the Rs.{shipping:.0f} shipping fee to make this an easy yes for you today."

        # ── 3. INCREASE AOV: Prefer Bundles / Complementary Cross-Sells
        elif objective == 'increase_aov':
            partner = find_bundle_partner(product)
            if partner:
                action = "recommend_bundle"
                confidence = 0.86
                bundle_total = product['price'] + partner['price']
                reasoning = "Objective is Increase Average Order Value. Converting objection into a high-value bundle with complementary accessory."
                customer_message = f"Instead of buying just one item, pair **{product['name']}** with **{partner['name']}** for Rs.{bundle_total:,.0f} total — a complete bundle that offers much higher value."
            else:
                action = "offer_free_shipping"
                confidence = 0.72
                reasoning = "Objective is Increase AOV. No bundle partner in stock; offering free shipping to preserve cart."
                customer_message = f"I can waive shipping on **{product['name']}** to give you better value."

        elif objective == 'clear_inventory':
            if margin > min_margin + (product['price'] * max_disc / 100):
                action = "offer_discount"
                confidence = 0.82
                reasoning = "Objective is Clear Inventory. Applying discount to accelerate stock turnover."
                customer_message = f"I can apply a {max_disc:.0f}% discount to help you get **{product['name']}** right away."
            else:
                action = "offer_free_shipping"
                confidence = 0.74
                reasoning = "Objective is Clear Inventory with tight margin; waiving shipping fee."
                customer_message = f"I can offer free shipping on **{product['name']}** to get it delivered to you."

    elif signal == 'ready_to_buy':
        action = "prepare_checkout"
        confidence = 0.95
        reasoning = "Customer is ready to buy. Proceeding to checkout confirmation."
        customer_message = f"Let's get your **{product['name']}** ordered at Rs.{product['price']:,.0f}. Shall I confirm the purchase?"
    elif objective == 'increase_aov' and signal in ('general', 'feature_inquiry'):
        partner = find_bundle_partner(product)
        if partner:
            action = "recommend_bundle"
            confidence = 0.75
            reasoning = "Objective is Increase AOV. Proactively proposing a high-value bundle."
            customer_message = f"**{product['name']}** is great on its own, but pairs even better with **{partner['name']}**!"

    auto_disc = min(max_disc, threshold, 10.0) if action == 'offer_discount' else None
    disc_param = explicit_discount if explicit_discount is not None else auto_disc
    proposal = {
        "customer_state": f"{signal}_detected",
        "recommended_action": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "expected_outcome": "increase_conversion_probability",
        "action_params": {"discount_pct": disc_param, "customer_message": customer_message}
    }
    db.log_audit(session_id, "agent_decision_heuristic",
                 f"Heuristic proposed '{action}' (objective={objective}). {reasoning}", {"proposal": proposal})
    return proposal


# ─────────────────────────────────────────────────────────────────────────────
# 6. Backend Validation Layer (Hard Boundaries vs Approval Gates)
# ─────────────────────────────────────────────────────────────────────────────

def validate_proposal(session_id, proposal, product, quantity, merchant_settings, customer_memory):
    """
    Backend policy enforcer — the central Risk Gate.

    Tripartite Policy Architecture:
      1. HARD BOUNDARIES: Absolute safety limits (max discount cap, min margin floor, quantity cap, stock).
         Any violation is HARD BLOCKED immediately and CANNOT be overridden by merchant approval.
      2. APPROVAL GATES: Actions inside hard boundaries, but >= merchant approval threshold.
         Marked as HIGH risk and WAITING FOR MERCHANT APPROVAL.
      3. SAFE BOUNDS: Actions inside hard boundaries and < approval threshold.
         Auto-approved as APPROVED (LOW/MEDIUM risk).
    """
    action       = proposal.get('recommended_action', 'no_incentive')
    margin       = product['profit_margin']
    price        = product['price']
    original_amt = price * quantity
    max_disc     = float(merchant_settings.get('max_discount_pct', 20.0))
    min_margin   = float(merchant_settings.get('min_margin', 400.0))
    shipping     = float(merchant_settings.get('shipping_cost', 100.0))
    threshold    = float(merchant_settings.get('high_risk_discount_threshold', 10.0))
    inc_offered  = customer_memory.get('incentive_offered', 'none')

    # ── Hard Boundary 1: Quantity Limit (Hard cap = 5 units) ──────────────────
    if quantity > 5:
        rejection_reason = f"Quantity ({quantity}) exceeds absolute hard ceiling of 5 units per SKU."
        db.log_audit(session_id, "proposal_rejected",
                     f"Action '{action}' HARD BLOCKED: {rejection_reason}",
                     {"action": action, "quantity": quantity, "cap": 5})
        return {
            "approved":        False,
            "risk_level":      "HIGH",
            "approval_status": "BLOCKED",
            "approval_id":     None,
            "rejection_reason": rejection_reason,
            "final_action":    "no_incentive",
            "final_amount":    original_amt,
            "incentive":       "none",
            "validation_detail": f"HARD BLOCKED: Quantity limit exceeded ({quantity} > 5 units)."
        }

    # ── Hard Boundary 2: Stock Availability ───────────────────────────────────
    if product.get('stock', 0) < quantity or product.get('stock', 0) <= 0:
        rejection_reason = f"Requested item '{product['name']}' is out of stock ({product.get('stock', 0)} available)."
        db.log_audit(session_id, "proposal_rejected",
                     f"Action '{action}' HARD BLOCKED: {rejection_reason}",
                     {"action": action, "stock": product.get('stock', 0)})
        return {
            "approved":        False,
            "risk_level":      "HIGH",
            "approval_status": "BLOCKED",
            "approval_id":     None,
            "rejection_reason": rejection_reason,
            "final_action":    "no_incentive",
            "final_amount":    original_amt,
            "incentive":       "none",
            "validation_detail": f"HARD BLOCKED: Insufficient inventory."
        }

    # ── Discount Action Evaluation ────────────────────────────────────────────
    if action == 'offer_discount':
        proposed_pct = float((proposal.get('action_params') or {}).get('discount_pct') or max_disc)
        discount_val = original_amt * (proposed_pct / 100)
        remaining_margin = margin - discount_val

        # Hard Boundary Check A: Exceeds Maximum Hard Discount Cap
        if proposed_pct > max_disc:
            rejection_reason = f"Requested discount of {proposed_pct:.0f}% exceeds the absolute hard discount cap of {max_disc:.0f}%."
            db.log_audit(session_id, "proposal_rejected",
                         f"Action 'offer_discount' HARD BLOCKED: {rejection_reason}",
                         {"proposed_pct": proposed_pct, "max_disc": max_disc})
            return {
                "approved":        False,
                "risk_level":      "HIGH",
                "approval_status": "BLOCKED",
                "approval_id":     None,
                "rejection_reason": rejection_reason,
                "final_action":    "no_incentive",
                "final_amount":    original_amt,
                "incentive":       "none",
                "validation_detail": f"HARD BLOCKED: Exceeds hard cap of {max_disc:.0f}%."
            }

        # Hard Boundary Check B: Breaches Minimum Margin Floor
        if remaining_margin < min_margin:
            rejection_reason = f"Discount of {proposed_pct:.0f}% leaves unit margin at Rs.{remaining_margin:.0f}, which breaches the minimum margin floor of Rs.{min_margin:.0f}."
            db.log_audit(session_id, "proposal_rejected",
                         f"Action 'offer_discount' HARD BLOCKED: {rejection_reason}",
                         {"remaining_margin": remaining_margin, "min_margin": min_margin})
            return {
                "approved":        False,
                "risk_level":      "HIGH",
                "approval_status": "BLOCKED",
                "approval_id":     None,
                "rejection_reason": rejection_reason,
                "final_action":    "no_incentive",
                "final_amount":    original_amt,
                "incentive":       "none",
                "validation_detail": f"HARD BLOCKED: Breaches margin floor (Rs.{remaining_margin:.0f} < Rs.{min_margin:.0f})."
            }

        # Approval Gate Check: Inside Hard Bounds, but > Approval Threshold
        if proposed_pct > threshold:
            details = (
                f"AI proposed {proposed_pct:.0f}% discount on '{product['name']}' "
                f"(Rs.{original_amt:,.0f} order, margin Rs.{margin:,.0f}). "
                f"Within hard cap ({max_disc:.0f}%), but requires merchant approval (threshold {threshold:.0f}%)."
            )
            approval_id = db.create_pending_approval(
                session_id   = session_id,
                action_type  = action,
                product_id   = product['id'],
                product_name = product['name'],
                risk_level   = "HIGH",
                details      = details,
                discount_pct = proposed_pct,
                requested_amount = original_amt
            )
            db.log_audit(session_id, "risk_gate_high",
                         f"HIGH-risk action '{action}' ({proposed_pct:.0f}%) queued for merchant approval (id={approval_id}).",
                         {"action": action, "approval_id": approval_id, "proposed_pct": proposed_pct})
            return {
                "approved":        False,
                "risk_level":      "HIGH",
                "approval_status": "WAITING FOR MERCHANT APPROVAL",
                "approval_id":     approval_id,
                "rejection_reason": None,
                "final_action":    "no_incentive",
                "final_amount":    original_amt,
                "incentive":       "none",
                "validation_detail": f"Requires merchant approval (threshold {threshold:.0f}%, cap {max_disc:.0f}%)."
            }

        # Safe Bound: Inside hard cap & < approval threshold -> Auto-Approved
        final_amount = original_amt - discount_val
        incentive = f'GROWTH{int(proposed_pct)}'
        db.log_audit(session_id, "proposal_approved",
                     f"Discount auto-approved: {proposed_pct:.0f}% off, amount Rs.{final_amount:.2f}.",
                     {"action": action, "discount_pct": proposed_pct, "final_amount": final_amount,
                      "risk_level": "MEDIUM"})
        return {
            "approved":        True,
            "risk_level":      "MEDIUM",
            "approval_status": "APPROVED",
            "approval_id":     None,
            "rejection_reason": None,
            "final_action":    action,
            "final_amount":    final_amount,
            "incentive":       incentive,
            "validation_detail": "Policy validated. Action auto-approved within safe limits."
        }

    # ── Free Shipping Action Evaluation ───────────────────────────────────────
    elif action == 'offer_free_shipping':
        remaining_margin = margin - shipping
        if remaining_margin < 0:
            rejection_reason = f"Shipping fee waiver (Rs.{shipping:.0f}) exceeds total product margin (Rs.{margin:.0f})."
            db.log_audit(session_id, "proposal_rejected",
                         f"Action 'offer_free_shipping' HARD BLOCKED: {rejection_reason}",
                         {"shipping": shipping, "margin": margin})
            return {
                "approved":        False,
                "risk_level":      "HIGH",
                "approval_status": "BLOCKED",
                "approval_id":     None,
                "rejection_reason": rejection_reason,
                "final_action":    "no_incentive",
                "final_amount":    original_amt,
                "incentive":       "none",
                "validation_detail": "HARD BLOCKED: Shipping waiver exceeds margin."
            }
        final_amount = max(0.0, original_amt - shipping)
        incentive = 'FREESHIP'
        db.log_audit(session_id, "proposal_approved",
                     f"Free shipping auto-approved. Amount: Rs.{final_amount:.2f}.",
                     {"action": action, "final_amount": final_amount, "risk_level": "MEDIUM"})
        return {
            "approved":        True,
            "risk_level":      "MEDIUM",
            "approval_status": "APPROVED",
            "approval_id":     None,
            "rejection_reason": None,
            "final_action":    action,
            "final_amount":    final_amount,
            "incentive":       incentive,
            "validation_detail": "Policy validated. Shipping waiver auto-approved."
        }

    # ── Bundle Action Evaluation ──────────────────────────────────────────────
    elif action == 'recommend_bundle':
        partner = find_bundle_partner(product)
        if not partner:
            return {
                "approved":        True,
                "risk_level":      "LOW",
                "approval_status": "APPROVED",
                "approval_id":     None,
                "rejection_reason": None,
                "final_action":    "no_incentive",
                "final_amount":    original_amt,
                "incentive":       "none",
                "validation_detail": "No bundle partner in stock; fallback to standard catalog pricing."
            }
        db.log_audit(session_id, "proposal_approved",
                     f"Bundle auto-approved: '{product['name']}' + '{partner['name']}'.",
                     {"action": action, "partner": partner['name'], "risk_level": "LOW"})
        return {
            "approved":        True,
            "risk_level":      "LOW",
            "approval_status": "APPROVED",
            "approval_id":     None,
            "rejection_reason": None,
            "final_action":    action,
            "final_amount":    original_amt,
            "incentive":       "BUNDLE",
            "validation_detail": "Policy validated. Complementary bundle auto-approved."
        }

    # ── LOW-risk: cheap alternative / compare / clarify / checkout ────────────
    elif action in ('recommend_cheaper_alternative', 'compare_products',
                    'ask_clarifying_question', 'no_incentive', 'prepare_checkout'):
        db.log_audit(session_id, "proposal_approved",
                     f"LOW-risk action '{action}' auto-approved.",
                     {"action": action, "risk_level": "LOW"})
        return {
            "approved":        True,
            "risk_level":      "LOW",
            "approval_status": "APPROVED",
            "approval_id":     None,
            "rejection_reason": None,
            "final_action":    action,
            "final_amount":    original_amt,
            "incentive":       "none",
            "validation_detail": "Policy validated. Standard action auto-approved."
        }

    else:
        return {
            "approved":        False,
            "risk_level":      "HIGH",
            "approval_status": "BLOCKED",
            "approval_id":     None,
            "rejection_reason": f"Action '{action}' is not in supported policy whitelist.",
            "final_action":    "no_incentive",
            "final_amount":    original_amt,
            "incentive":       "none",
            "validation_detail": "HARD BLOCKED: Unsupported action."
        }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Strategy Executor
# ─────────────────────────────────────────────────────────────────────────────

def execute_strategy(session_id, validated, proposal, product, quantity, merchant_settings):
    """
    Execute a validated strategy. Returns the full result dict including:
    - response message to customer
    - decision_card for Agent Intelligence panel
    - decision_lifecycle steps
    - final_amount, incentive, alternative_product
    """
    action       = validated['final_action']
    final_amount = validated['final_amount']
    incentive    = validated['incentive']
    margin       = product['profit_margin']
    objective    = merchant_settings.get('objective', 'protect_profit')
    customer_msg = proposal.get('action_params', {}).get('customer_message', '')

    alternative_product = None
    bundle_partner      = None
    compare_products    = None
    strategy_key        = action  # for audit log

    # ── Cheaper alternative ───────────────────────────────────────────────────
    if action == 'recommend_cheaper_alternative':
        category_products = db.get_products(product['category'])
        cheapest = None
        for p in category_products:
            if p['price'] < product['price'] and p['stock'] > 0:
                if cheapest is None or p['price'] < cheapest['price']:
                    cheapest = p
        if cheapest:
            alternative_product = cheapest
            final_amount = cheapest['price'] * quantity
            incentive = 'none'
            if not customer_msg or 'cheaper' not in customer_msg.lower():
                customer_msg = (
                    f"Since price is a concern, I recommend **{cheapest['name']}** at "
                    f"Rs.{cheapest['price']:,.0f} — it covers 90% of the same features at a better price."
                )
        else:
            # Nothing cheaper — fall back to no_incentive
            action = 'no_incentive'
            customer_msg = (
                f"This is our most affordable option in this category. "
                f"**{product['name']}** at Rs.{product['price']:,.0f} is the best value available."
            )

    # ── Bundle ────────────────────────────────────────────────────────────────
    elif action == 'recommend_bundle':
        partner = find_bundle_partner(product)
        if partner:
            bundle_partner = partner
            bundle_total = product['price'] * quantity + partner['price']
            final_amount = bundle_total
            incentive = 'BUNDLE'
            customer_msg = (
                f"I recommend pairing **{product['name']}** (Rs.{product['price']:,.0f}) with "
                f"**{partner['name']}** (Rs.{partner['price']:,.0f}) — "
                f"a bundle total of Rs.{bundle_total:,.0f} for a complete experience."
            )
        else:
            action = 'no_incentive'
            customer_msg = customer_msg or f"**{product['name']}** is a great choice at Rs.{product['price']:,.0f}."

    # ── Compare products ──────────────────────────────────────────────────────
    elif action == 'compare_products':
        category_products = [p for p in db.get_products(product['category']) if p['id'] != product['id'] and p['stock'] > 0]
        if category_products:
            alt = min(category_products, key=lambda p: abs(p['price'] - product['price']))
            compare_products = [product, alt]
            customer_msg = (
                f"Here are two options for you to compare:\n\n"
                f"**{product['name']}** — Rs.{product['price']:,.0f} | {product['description'][:80]}\n\n"
                f"**{alt['name']}** — Rs.{alt['price']:,.0f} | {alt['description'][:80]}\n\n"
                f"Which would you prefer?"
            )

    # ── Discount ──────────────────────────────────────────────────────────────
    elif action == 'offer_discount':
        max_disc = merchant_settings.get('max_discount_pct', 10.0)
        disc_val = product['price'] * quantity * (max_disc / 100)
        final_amount = product['price'] * quantity - disc_val
        incentive = 'GROWTH10'
        customer_msg = customer_msg or (
            f"Good news! I'm applying a {max_disc:.0f}% discount on **{product['name']}**. "
            f"Your price: Rs.{final_amount:,.0f}."
        )

    # ── Free shipping ─────────────────────────────────────────────────────────
    elif action == 'offer_free_shipping':
        shipping = merchant_settings.get('shipping_cost', 100.0)
        final_amount = max(0.0, product['price'] * quantity - shipping)
        incentive = 'FREESHIP'
        customer_msg = customer_msg or (
            f"I'm waiving the Rs.{shipping:.0f} shipping fee on your order. "
            f"**{product['name']}** is yours at Rs.{final_amount:,.0f}."
        )

    # ── No incentive / prepare checkout ──────────────────────────────────────
    else:
        final_amount = product['price'] * quantity
        customer_msg = customer_msg or (
            f"**{product['name']}** is available at Rs.{product['price']:,.0f}. "
            f"Ready to confirm your purchase?"
        )

    audit_id = db.log_audit(session_id, strategy_key,
                            f"Strategy '{action}' executed. Amount: Rs.{final_amount:.2f}, Incentive: {incentive}.",
                            {"product_id": product['id'], "final_amount": final_amount, "incentive": incentive,
                             "objective": objective})

    # ── Build decision card (Privacy-safe: no internal cost price or raw margin numbers) ───
    obj_label = OBJECTIVE_LABELS.get(objective, objective)
    risk_level      = validated.get('risk_level', 'LOW')
    approval_status = validated.get('approval_status', 'APPROVED')
    decision_card = {
        "signal": proposal.get('customer_state', 'general').replace('_', ' ').title(),
        "analysis": {
            "purchase_intent":  _intent_level(proposal.get('customer_state', '')),
            "price_sensitivity": _sensitivity_level(validated.get('final_action', '')),
            "margin_health":    "Protected (Safe)",
            "merchant_objective": obj_label,
            "confidence":       f"{proposal.get('confidence', 0.7):.0%}"
        },
        "decision": action.replace('_', ' ').title(),
        "risk_level":       risk_level,
        "approval_status":  approval_status,
        "approval_id":      validated.get('approval_id'),
        "validation_status": approval_status,
        "incentive_applied": incentive,
        "audit_id":         audit_id,
        "reasoning": proposal.get('reasoning', ''),
        "outcome": proposal.get('expected_outcome', 'improve_conversion_probability').replace('_', ' ').title()
    }

    return {
        "strategy": action,
        "incentive": incentive,
        "final_amount": final_amount,
        "audit_id": audit_id,
        "reasoning": customer_msg,
        "decision_card": decision_card,
        "alternative_product": alternative_product,
        "bundle_partner": bundle_partner,
        "compare_products": compare_products
    }


def _intent_level(customer_state):
    if 'high' in customer_state: return 'High'
    if 'ready' in customer_state: return 'Very High'
    if 'low' in customer_state: return 'Low'
    return 'Medium'

def _sensitivity_level(action):
    if action in ('offer_discount', 'offer_free_shipping'): return 'High'
    if action == 'no_incentive': return 'Low'
    return 'Medium'


# ─────────────────────────────────────────────────────────────────────────────
# 8. Guardrails (unchanged, still enforced after strategy execution)
# ─────────────────────────────────────────────────────────────────────────────

def check_guardrails(session_id, product, quantity, final_amount):
    if quantity > 5:
        reason = f"Quantity {quantity} exceeds security limit of 5. Human escalation required."
        db.log_audit(session_id, "guardrail_block", reason,
                     {"product_id": product['id'], "quantity": quantity, "amount": final_amount})
        return {"allowed": False, "escalate": True, "extra_confirm": False,
                "reason": "This order exceeds the quantity safety threshold of 5 items. Human verification is required."}

    if final_amount > 5000:
        reason = f"Order total Rs.{final_amount:.2f} exceeds Rs.5,000 threshold. Double confirmation required."
        db.log_audit(session_id, "guardrail_check", reason,
                     {"product_id": product['id'], "quantity": quantity, "amount": final_amount})
        return {"allowed": True, "escalate": False, "extra_confirm": True,
                "reason": f"Your total is Rs.{final_amount:,.0f} (above Rs.5,000 threshold). Please confirm to proceed."}

    db.log_audit(session_id, "guardrail_check", f"Order Rs.{final_amount:.2f} passed all guardrails.",
                 {"product_id": product['id'], "quantity": quantity, "amount": final_amount})
    return {"allowed": True, "escalate": False, "extra_confirm": False,
            "reason": f"Ready to confirm: {quantity}x **{product['name']}** for Rs.{final_amount:,.0f}?"}


# ─────────────────────────────────────────────────────────────────────────────
# 9. Abandoned Checkout Recovery
# ─────────────────────────────────────────────────────────────────────────────

def generate_recovery_message(session_id, abandoned_event, merchant_settings):
    """
    Generate a personalized recovery message for an abandoned checkout.
    Does NOT offer a new incentive if one was already used.
    """
    product_name   = abandoned_event.get('product_name', 'your selected product')
    amount         = abandoned_event.get('amount', 0)
    incentive_used = abandoned_event.get('incentive_used', 'none')
    memory         = db.get_customer_memory(session_id)
    prior_objection = memory.get('last_objection', 'general')
    objective       = merchant_settings.get('objective', 'protect_profit')

    already_had_incentive = incentive_used != 'none'

    if CLAUDE_API_KEY and not already_had_incentive:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            prompt = (
                f"A customer abandoned checkout for '{product_name}' (Rs.{amount:,.0f}).\n"
                f"Prior objection: {prior_objection}.\n"
                f"No incentive was previously offered.\n"
                f"Merchant objective: {OBJECTIVE_LABELS.get(objective, objective)}.\n\n"
                "Write a SHORT, warm, one-paragraph recovery message (max 40 words). "
                "Do not promise a specific discount — just invite them back. No markdown."
            )
            resp = client.messages.create(
                model="claude-3-5-sonnet-20241022", max_tokens=100, temperature=0.5,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text.strip()
        except Exception:
            pass

    # Fallback recovery messages
    if already_had_incentive:
        return (
            f"Your {product_name} checkout is still active with your previously applied benefit. "
            f"Ready to complete your purchase at Rs.{amount:,.0f}?"
        )
    return (
        f"You left {product_name} behind! It's still in your cart at Rs.{amount:,.0f}. "
        f"Complete your purchase now before stock runs out."
    )
