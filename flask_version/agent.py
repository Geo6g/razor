import os
import json
import re
from dotenv import load_dotenv
import db

# Load environment variables
load_dotenv()

CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')

CATALOG_PATH = os.path.join(os.path.dirname(__file__), 'data', 'catalog.json')

def load_catalog():
    """Load the fake merchant catalog from the JSON file."""
    try:
        with open(CATALOG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading catalog: {e}")
        return []

def fallback_parse(message, current_state='idle'):
    """
    Keyword-based fallback intent parser. Used if the LLM call fails.
    
    Args:
        message (str): Lowercased user text.
        current_state (str): Current conversational state of the user session.
        
    Returns:
        dict: Parsed intent dictionary.
    """
    msg = message.lower().strip()
    
    # Tokenize message to avoid partial word match issues (e.g. 'n' matching in 'running')
    tokens = set(re.findall(r'\b\w+\b', msg))
    
    # Check confirmation keywords
    confirm_words = {'yes', 'confirm', 'proceed', 'pay', 'correct', 'sure', 'ok', 'yea', 'yeah', 'yep', 'y'}
    if tokens.intersection(confirm_words) or 'lets go' in msg or "let's go" in msg:
        return {"action": "confirm", "query": None, "max_price": None, "quantity": 1}
        
    # Check cancellation keywords
    cancel_words = {'no', 'cancel', 'stop', 'abort', 'nope', 'dont', 'n', 'nevermind'}
    if tokens.intersection(cancel_words) or 'never mind' in msg or "don't" in msg:
        return {"action": "cancel", "query": None, "max_price": None, "quantity": 1}
        
    # Extract quantity (look for numbers)
    quantity = 1
    # Match strings like "3 shoes", "quantity 2", "buy 5", etc.
    quantity_match = re.search(r'\b(\d+)\b', msg)
    if quantity_match:
        val = int(quantity_match.group(1))
        # Ensure we don't accidentally parse a product ID or price as quantity
        # If it's isolated or precedes a product noun, use it.
        # Simple safeguard: keep it if it's <= 100
        if val > 0 and val < 100:
            quantity = val
            
    # Extract max price (look for "under ₹5000", "below 1000", "max 2000", etc.)
    max_price = None
    price_match = re.search(r'(?:under|below|max|budget|within|price)\s*(?:rs\.?|inr|rupees|₹)?\s*(\d+(?:\.\d+)?)', msg)
    if price_match:
        max_price = float(price_match.group(1))
    
    # Try to extract search query
    # Strip common command verbs and quantities to isolate the search term
    clean_query = msg
    clean_query = re.sub(r'\b(buy|order|search|find|get|want|need|show|look for|purchase)\b', '', clean_query)
    clean_query = re.sub(r'\b\d+\b', '', clean_query) # remove quantity number
    clean_query = re.sub(r'\b(under|below|max|budget|within|price)\s*(?:rs\.?|inr|rupees|₹)?\s*\d+(?:\.\d+)?\b', '', clean_query) # remove price constraint
    clean_query = re.sub(r'\b(items|pcs|units|pieces|of)\b', '', clean_query)
    clean_query = clean_query.strip()
    
    if len(clean_query) > 1:
        action = "search"
        query = clean_query
    else:
        action = "unclear"
        query = None
        
    return {
        "action": action,
        "query": query,
        "max_price": max_price,
        "quantity": quantity
    }

def parse_intent(session_id, message, current_state='idle'):
    """
    Parse the user's raw message using Anthropic Claude API, with a keyword fallback.
    
    Args:
        session_id (str): User session ID.
        message (str): Raw user text input.
        current_state (str): Current state machine state.
        
    Returns:
        dict: Parsed intent.
    """
    # 1. Check if user is confirming or canceling directly using basic keyword checks
    # to avoid LLM lag or misinterpretation for trivial answers.
    msg_lower = message.lower().strip()
    if msg_lower in ['yes', 'confirm', 'y', 'proceed', 'lets go', 'let\'s go'] and current_state == 'awaiting_confirmation':
        intent = {"action": "confirm", "query": None, "max_price": None, "quantity": 1}
        db.log_audit(
            session_id=session_id,
            action_type="intent_parsed",
            reasoning="Fast-path confirmation detected via keyword matching.",
            payload={"user_message": message, "intent": intent}
        )
        return intent
        
    if msg_lower in ['no', 'cancel', 'n', 'stop', 'abort'] and current_state == 'awaiting_confirmation':
        intent = {"action": "cancel", "query": None, "max_price": None, "quantity": 1}
        db.log_audit(
            session_id=session_id,
            action_type="intent_parsed",
            reasoning="Fast-path cancellation detected via keyword matching.",
            payload={"user_message": message, "intent": intent}
        )
        return intent

    # 2. Attempt Claude parsing
    if CLAUDE_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            
            system_prompt = (
                "You are an intent parser for an AI E-commerce Checkout agent. "
                "Analyze the user's message and return ONLY a JSON object. "
                "Do not include any greeting, explanation, conversational preamble, or markdown formatting other than the JSON itself. "
                "JSON Schema:\n"
                "{\n"
                "  \"action\": \"search\" | \"confirm\" | \"cancel\" | \"unclear\",\n"
                "  \"query\": string or null (product name, description words, or search queries),\n"
                "  \"max_price\": number or null (price limit if mentioned, else null),\n"
                "  \"quantity\": integer (default to 1)\n"
                "}\n\n"
                "Examples:\n"
                "- 'i want 3 yoga mats' -> {\"action\": \"search\", \"query\": \"yoga mats\", \"max_price\": null, \"quantity\": 3}\n"
                "- 'sure, go ahead' -> {\"action\": \"confirm\", \"query\": null, \"max_price\": null, \"quantity\": 1}\n"
                "- 'cancel it' -> {\"action\": \"cancel\", \"query\": null, \"max_price\": null, \"quantity\": 1}\n"
                "- 'something under 2000 rupees' -> {\"action\": \"search\", \"query\": \"something\", \"max_price\": 2000.0, \"quantity\": 1}"
            )
            
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                temperature=0.0,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Parse the user message: \"{message}\" (Current conversational state: {current_state})"}
                ]
            )
            
            response_text = response.content[0].text.strip()
            
            # Clean up potential markdown formatting (e.g. ```json ... ```)
            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
                
            intent = json.loads(json_str)
            
            # Validate structure
            required_keys = {'action', 'query', 'max_price', 'quantity'}
            if all(k in intent for k in required_keys):
                db.log_audit(
                    session_id=session_id,
                    action_type="intent_parsed",
                    reasoning="Intent parsed successfully using Anthropic Claude API.",
                    payload={"user_message": message, "raw_response": response_text, "intent": intent}
                )
                return intent
            else:
                raise ValueError("Parsed JSON missing required keys.")
                
        except Exception as e:
            db.log_audit(
                session_id=session_id,
                action_type="intent_parsed_warning",
                reasoning=f"LLM Parsing failed, falling back to keyword parser. Error: {str(e)}",
                payload={"user_message": message, "error": str(e)}
            )
    else:
        db.log_audit(
            session_id=session_id,
            action_type="intent_parsed_warning",
            reasoning="CLAUDE_API_KEY is missing. Using keyword fallback parser.",
            payload={"user_message": message}
        )

    # 3. Fallback parser
    intent = fallback_parse(message, current_state)
    db.log_audit(
        session_id=session_id,
        action_type="intent_parsed",
        reasoning="Intent parsed using keyword-based fallback parser.",
        payload={"user_message": message, "intent": intent}
    )
    return intent

def match_product(session_id, query, max_price=None, quantity=1):
    """
    Matches parsed search intent against the merchant catalog using token scoring.
    
    Args:
        session_id (str): Session ID.
        query (str): Search term.
        max_price (float, optional): Maximum budget.
        quantity (int): Ordered quantity.
        
    Returns:
        tuple: (best_match_product, reason_msg)
    """
    if not query:
        return None, "No search term provided."
        
    catalog = load_catalog()
    query_tokens = query.lower().split()
    
    scored_products = []
    
    for product in catalog:
        score = 0
        name_lower = product['name'].lower()
        desc_lower = product['description'].lower()
        cat_lower = product['category'].lower()
        
        # 1. Exact match bonus
        if query.lower() == name_lower:
            score += 150
        elif query.lower() in name_lower:
            score += 50
            
        # 2. Token overlap scoring
        for token in query_tokens:
            if token in name_lower:
                score += 20
            if token in cat_lower:
                score += 10
            if token in desc_lower:
                score += 3
                
        # 3. Filter by price if max_price is defined
        if max_price is not None and product['price'] > max_price:
            score = -1 # Disqualify
            
        if score > 0:
            scored_products.append((product, score))
            
    # Sort by score descending
    scored_products.sort(key=lambda x: x[1], reverse=True)
    
    # Logging search details
    payload_info = {
        "query": query,
        "max_price": max_price,
        "quantity": quantity,
        "candidates_found": len(scored_products)
    }
    
    if not scored_products:
        reason = f"No catalog product matched search query '{query}' under budget limit."
        db.log_audit(session_id, "search_match_failed", reason, payload=payload_info)
        return None, "No matching products found. Try a different description."
        
    best_match = scored_products[0][0]
    payload_info["matched_product"] = best_match
    
    # 4. Check Stock
    if best_match['stock'] < quantity:
        reason = f"Product '{best_match['name']}' matches query but stock is insufficient (Requested {quantity}, Stock {best_match['stock']})."
        db.log_audit(session_id, "search_match_failed", reason, payload=payload_info)
        return best_match, f"Product '{best_match['name']}' is out of stock (only {best_match['stock']} remaining)."
        
    reason = f"Search matched product '{best_match['name']}' (Score: {scored_products[0][1]}) for query '{query}'."
    db.log_audit(session_id, "search_match_success", reason, payload=payload_info)
    return best_match, "Success"

def check_guardrails(session_id, product, quantity):
    """
    Validate safety guardrails for the order.
    
    1. Quantity limit: blocks quantity > 5 (escalates).
    2. High-value limit: requires secondary confirmation if total > ₹5000.
    
    Args:
        session_id (str): Session ID.
        product (dict): Catalog product.
        quantity (int): Ordered quantity.
        
    Returns:
        dict: Guardrail status { 'allowed': bool, 'escalate': bool, 'extra_confirm': bool, 'reason': str }
    """
    total_amount = product['price'] * quantity
    
    # 1. Quantity Check
    if quantity > 5:
        reason = f"Guardrail Alert: Quantity {quantity} exceeds the safety threshold of 5. Order blocked. Human escalation required."
        db.log_audit(
            session_id=session_id,
            action_type="guardrail_block",
            reasoning=reason,
            payload={"product_id": product['id'], "quantity": quantity, "total_amount": total_amount}
        )
        return {
            "allowed": False,
            "escalate": True,
            "extra_confirm": False,
            "reason": "Quantity limit exceeded (maximum 5 items). This order requires manual verification and human escalation."
        }
        
    # 2. High-Value Check
    if total_amount > 5000:
        reason = f"Guardrail Alert: Total value of ₹{total_amount:.2f} exceeds standard limit of ₹5000. Forcing secondary high-value confirmation."
        db.log_audit(
            session_id=session_id,
            action_type="guardrail_check",
            reasoning=reason,
            payload={"product_id": product['id'], "quantity": quantity, "total_amount": total_amount}
        )
        return {
            "allowed": True,
            "escalate": False,
            "extra_confirm": True,
            "reason": f"This order totals ₹{total_amount:,.2f}, which is above the ₹5,000 safety limit. Please type 'confirm' or 'yes' to proceed with payment."
        }
        
    # 3. Passed within normal boundaries
    reason = f"Guardrail Check Passed: Order of {quantity}x '{product['name']}' (Total: ₹{total_amount:.2f}) complies with safety rules."
    db.log_audit(
        session_id=session_id,
        action_type="guardrail_check",
        reasoning=reason,
        payload={"product_id": product['id'], "quantity": quantity, "total_amount": total_amount}
    )
    return {
        "allowed": True,
        "escalate": False,
        "extra_confirm": False,
        "reason": f"Would you like to confirm the purchase of {quantity}x '{product['name']}' for ₹{total_amount:,.2f}?"
    }
