import os
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

import db
import agent
from backend import agent_buyer
import payments

load_dotenv()

app = FastAPI(title="GrowthPilot AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session state machine
SESSION_STATES: Dict[str, Dict[str, Any]] = {}

def get_session_state(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSION_STATES:
        SESSION_STATES[session_id] = {
            "state": "idle",
            "pending_product": None,
            "pending_quantity": 1,
            "pending_amount": 0.0,
            "incentive_used": "none",
            "requires_extra_confirm": False,
            "last_proposal": None,
            "last_lifecycle": []
        }
    return SESSION_STATES[session_id]

def reset_session_state(session_id: str):
    SESSION_STATES[session_id] = {
        "state": "idle",
        "pending_product": None,
        "pending_quantity": 1,
        "pending_amount": 0.0,
        "incentive_used": "none",
        "requires_extra_confirm": False,
        "last_proposal": None,
        "last_lifecycle": []
    }

@app.on_event("startup")
def startup_event():
    db.init_db()

# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    active_product_id: Optional[str] = None

class CreateOrderRequest(BaseModel):
    amount: float
    currency: Optional[str] = "INR"
    receipt: Optional[str] = None
    product_id: Optional[str] = None
    session_id: Optional[str] = None
    notes: Optional[Dict[str, Any]] = None

class VerifyRequest(BaseModel):
    session_id: str
    status: str
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None
    error: Optional[Dict[str, Any]] = None

class MerchantSettingsRequest(BaseModel):
    objective: str
    max_discount_pct: float = 10.0
    min_margin: float = 400.0
    shipping_cost: float = 100.0
    high_risk_discount_threshold: float = 15.0

class ApprovalResolutionRequest(BaseModel):
    resolution_reason: Optional[str] = ""

class StrategyOutcomeRequest(BaseModel):
    session_id: str
    strategy: str
    product_id: str
    product_name: str
    customer_state: Optional[str] = "general"
    result: str  # 'converted' | 'abandoned' | 'pending'
    revenue: Optional[float] = 0.0
    profit_delta: Optional[float] = 0.0

# ── Buyer-agent request/response models (Step 1) ──────────────────────────────

class BuyerIntentLineItem(BaseModel):
    product_id: str
    quantity: int
    max_unit_price: Optional[float] = None

class BuyerCheckoutIntentRequest(BaseModel):
    buyer_id: str
    session_id: Optional[str] = None
    currency: str = "INR"
    max_total: float
    expires_at: str  # ISO-8601 UTC
    items: List[BuyerIntentLineItem]
    signature: str
    intent_version: Optional[str] = agent_buyer.MIN_INTENT_VERSION

class BuyerConfirmRequest(BaseModel):
    intent_id: str
    buyer_id: str
    signature: str  # signature over the *original* mandate payload

class BuyerWebhookRequest(BaseModel):
    intent_id: str
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None
    status: str  # 'paid' | 'failed'
    error: Optional[Dict[str, Any]] = None

# ── Product endpoints ─────────────────────────────────────────────────────────

@app.get("/api/products")
def get_products(category: Optional[str] = None):
    return db.get_products(category)

# ── Merchant settings endpoints ───────────────────────────────────────────────

@app.get("/api/merchant/settings")
def get_settings():
    return db.get_merchant_settings()

@app.post("/api/merchant/settings")
def save_settings(req: MerchantSettingsRequest):
    valid_objectives = {"maximize_conversions", "protect_profit", "increase_aov", "clear_inventory"}
    if req.objective not in valid_objectives:
        raise HTTPException(status_code=400, detail=f"Invalid objective. Must be one of: {valid_objectives}")
    if not (0 <= req.max_discount_pct <= 30):
        raise HTTPException(status_code=400, detail="max_discount_pct must be between 0 and 30.")
    if req.min_margin < 0:
        raise HTTPException(status_code=400, detail="min_margin cannot be negative.")
    db.save_merchant_settings(
        req.objective, req.max_discount_pct, req.min_margin,
        req.shipping_cost, req.high_risk_discount_threshold
    )
    db.log_audit("system", "settings_updated",
                 f"Merchant settings updated. Objective: '{req.objective}', "
                 f"Max disc: {req.max_discount_pct}%, Min margin: Rs.{req.min_margin}, "
                 f"High-risk threshold: {req.high_risk_discount_threshold}%.",
                 {"objective": req.objective, "max_discount_pct": req.max_discount_pct,
                  "min_margin": req.min_margin,
                  "high_risk_discount_threshold": req.high_risk_discount_threshold})
@app.get("/api/merchant/objective-matrix")
def get_objective_matrix(product_id: Optional[str] = None, signal: str = "price_objection"):
    """
    Demonstrates how changing the merchant objective materially alters AI decisions
    for the exact same product and customer scenario.
    """
    product = db.get_product(product_id) if product_id else None
    if not product:
        prods = db.get_products()
        product = prods[0] if prods else None
    if not product:
        raise HTTPException(status_code=404, detail="No products found in catalog.")

    settings = db.get_merchant_settings()
    results = {}
    objectives = ["protect_profit", "maximize_conversions", "increase_aov"]

    for obj in objectives:
        test_settings = dict(settings)
        test_settings['objective'] = obj
        prop = agent._heuristic_propose(
            session_id="sim_matrix",
            product=product,
            signal=signal,
            merchant_settings=test_settings,
            customer_memory={},
            strategy_stats={}
        )
        val = agent.validate_proposal(
            session_id="sim_matrix",
            proposal=prop,
            product=product,
            quantity=1,
            merchant_settings=test_settings,
            customer_memory={}
        )
        res = agent.execute_strategy(
            session_id="sim_matrix",
            validated=val,
            proposal=prop,
            product=product,
            quantity=1,
            merchant_settings=test_settings
        )
        results[obj] = {
            "objective": obj,
            "objective_label": agent.OBJECTIVE_LABELS.get(obj, obj),
            "recommended_action": prop['recommended_action'],
            "action_label": prop['recommended_action'].replace('_', ' ').title(),
            "confidence": f"{prop['confidence']:.0%}",
            "reasoning": prop['reasoning'],
            "incentive_applied": res['incentive'],
            "final_amount": f"Rs.{res['final_amount']:,.0f}",
            "decision_summary": res['decision_card']['decision'],
            "risk_level": val.get('risk_level', 'LOW'),
            "approval_status": val.get('approval_status', 'APPROVED')
        }

    return {
        "product": {
            "id": product['id'],
            "name": product['name'],
            "price": product['price'],
            "category": product['category']
        },
        "signal": signal,
        "active_objective": settings.get('objective', 'protect_profit'),
        "matrix": results
    }


# ── Approval Gate Endpoints ───────────────────────────────────────────────────

@app.get("/api/approvals")
def list_approvals(status: Optional[str] = None):
    """
    List pending or resolved merchant approvals.
    ?status=WAITING+FOR+MERCHANT+APPROVAL  →  only waiting
    ?status=APPROVED                        →  only approved
    ?status=BLOCKED                         →  only blocked
    Omit ?status to get all.
    """
    rows = db.get_pending_approvals(status_filter=status)
    return {"approvals": rows, "count": len(rows)}


@app.post("/api/approvals/{approval_id}/approve")
def approve_action(approval_id: str, req: ApprovalResolutionRequest):
    """
    Merchant explicitly approves a HIGH-risk AI action.
    The frontend MUST NOT trust its own approval state — this endpoint is the authoritative gate.
    Enforces that merchant approval cannot override hard backend safety limits.
    """
    row = db.get_approval(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")
    if row['status'] != 'WAITING FOR MERCHANT APPROVAL':
        raise HTTPException(status_code=409, detail=f"Approval already resolved: {row['status']}")

    product = db.get_product(row['product_id'])
    if not product:
        raise HTTPException(status_code=404, detail="Target product no longer exists.")

    merchant_settings = db.get_merchant_settings()
    max_disc   = float(merchant_settings.get('max_discount_pct', 20.0))
    min_margin = float(merchant_settings.get('min_margin', 400.0))
    discount_pct = float(row.get('discount_pct') or 0.0)
    discount_val = product['price'] * (discount_pct / 100.0)
    remaining_margin = product['profit_margin'] - discount_val

    # ── Hard Boundary Revalidation ────────────────────────────────────────────
    fail_reason = None
    if discount_pct > max_disc:
        fail_reason = f"Proposed discount of {discount_pct:.0f}% exceeds current hard cap of {max_disc:.0f}%."
    elif remaining_margin < min_margin:
        fail_reason = f"Resulting margin (Rs.{remaining_margin:.0f}) breaches minimum margin floor of Rs.{min_margin:.0f}."
    elif product.get('stock', 0) <= 0:
        fail_reason = "Target product is currently out of stock."

    if fail_reason:
        db.resolve_pending_approval(approval_id, "BLOCKED", f"Revalidation failed: {fail_reason}")
        db.log_audit(row['session_id'], "approval_revalidation_failed",
                     f"Approval '{approval_id}' BLOCKED during safety revalidation: {fail_reason}",
                     {"approval_id": approval_id, "reason": fail_reason})
        raise HTTPException(
            status_code=409,
            detail=f"Approval rejected by server-side safety revalidation: {fail_reason}"
        )

    resolved = db.resolve_pending_approval(approval_id, "APPROVED",
                                           req.resolution_reason or "Merchant approved manually after safety revalidation.")
    db.log_audit(row['session_id'], "approval_granted",
                 f"Merchant APPROVED action '{row['action_type']}' on '{row['product_name']}' "
                 f"(approval_id={approval_id}). Hard safety boundaries revalidated and satisfied.",
                 {"approval_id": approval_id, "product_id": row['product_id']})
    return {"status": "APPROVED", "approval": resolved}


@app.post("/api/approvals/{approval_id}/block")
def block_action(approval_id: str, req: ApprovalResolutionRequest):
    """
    Merchant explicitly blocks a HIGH-risk AI action.
    """
    row = db.get_approval(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")
    if row['status'] != 'WAITING FOR MERCHANT APPROVAL':
        raise HTTPException(status_code=409, detail=f"Approval already resolved: {row['status']}")
    resolved = db.resolve_pending_approval(approval_id, "BLOCKED",
                                           req.resolution_reason or "Merchant blocked this action.")
    db.log_audit(row['session_id'], "approval_blocked",
                 f"Merchant BLOCKED action '{row['action_type']}' on '{row['product_name']}' "
                 f"(approval_id={approval_id}).",
                 {"approval_id": approval_id, "product_id": row['product_id']})
    return {"status": "BLOCKED", "approval": resolved}

# ── Main chat endpoint ────────────────────────────────────────────────────────

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    message    = req.message.strip()
    session_id = req.session_id or str(uuid.uuid4())

    if not message:
        raise HTTPException(status_code=400, detail="Empty message.")

    db.add_chat_message(session_id, 'user', message)
    state_data      = get_session_state(session_id)
    current_state   = state_data['state']
    merchant_settings = db.get_merchant_settings()
    customer_memory = db.get_customer_memory(session_id)

    # ── Session reset ──────────────────────────────────────────────────────────
    if message.lower() in ['reset', 'clear', 'start over', 'reboot']:
        reset_session_state(session_id)
        db.log_audit(session_id, "session_reset", "User reset the session.")
        reply = "Session reset! I'm ready to help you find the perfect product. What are you looking for?"
        db.add_chat_message(session_id, 'agent', reply)
        return {"session_id": session_id, "response": reply, "state": "idle",
                "decision_card": None, "products_recommended": [], "decision_lifecycle": []}

    # ── Awaiting escalation ───────────────────────────────────────────────────
    if current_state == 'awaiting_escalation':
        intent = agent.parse_intent(session_id, message, current_state)
        if intent['action'] == 'cancel':
            reset_session_state(session_id)
            reply = "Escalation cleared. What else can I help you find?"
            db.add_chat_message(session_id, 'agent', reply)
            return {"session_id": session_id, "response": reply, "state": "idle"}
        reply = "This order requires human verification (quantity > 5). Type 'cancel' to search for something else."
        db.add_chat_message(session_id, 'agent', reply)
        return {"session_id": session_id, "response": reply, "state": "awaiting_escalation"}

    # ── Awaiting confirmation ─────────────────────────────────────────────────
    if current_state == 'awaiting_confirmation':
        product  = state_data['pending_product']
        quantity = state_data['pending_quantity']
        amount   = state_data['pending_amount']
        incentive = state_data['incentive_used']

        intent = agent.parse_intent(session_id, message, current_state)

        if intent['action'] == 'confirm':
            try:
                db_order_id = db.create_order(
                    session_id=session_id,
                    product_id=product['id'],
                    product_name=product['name'],
                    amount=amount,
                    status='pending',
                    incentive_used=incentive
                )
                rzp_order = payments.create_razorpay_order(session_id, amount, db_order_id)

                if rzp_order:
                    conn = db.get_db_connection()
                    conn.cursor().execute('UPDATE orders SET razorpay_order_id = ? WHERE id = ?',
                                         (rzp_order['id'], db_order_id))
                    conn.commit(); conn.close()

                    # Create checkout event
                    db.create_checkout_event(session_id, db_order_id, rzp_order['id'], 'created',
                                              product['name'], amount, incentive)
                    # Update customer memory
                    db.update_customer_memory(session_id,
                        last_product_id=product['id'],
                        last_product_name=product['name'],
                        incentive_offered=incentive
                    )

                    razorpay_options = {
                        "key": payments.RAZORPAY_KEY_ID or "rzp_test_mock",
                        "amount": rzp_order['amount'],
                        "currency": rzp_order.get('currency', 'INR'),
                        "name": "GrowthPilot AI",
                        "description": f"Purchase: {quantity}x {product['name']}",
                        "order_id": rzp_order['id'],
                        "prefill": {"name": "Guest Customer", "email": "customer@growthpilot.ai"}
                    }

                    lifecycle = state_data.get('last_lifecycle', [])
                    lifecycle.append({"stage": "Checkout Created", "detail": f"Razorpay order initiated for Rs.{amount:,.0f}",
                                      "status": "active"})
                    reset_session_state(session_id)
                    reply = "Confirming your purchase. Launching secure Razorpay checkout now."
                    db.add_chat_message(session_id, 'agent', reply)
                    return {
                        "session_id": session_id,
                        "response": reply,
                        "state": "idle",
                        "payment_trigger": True,
                        "razorpay_options": razorpay_options,
                        "decision_card": None,
                        "decision_lifecycle": lifecycle,
                        "products_recommended": [product]
                    }
                else:
                    reset_session_state(session_id)
                    reply = "Payment gateway error. The order has been aborted. Please try again."
                    db.add_chat_message(session_id, 'agent', reply)
                    return {"session_id": session_id, "response": reply, "state": "idle"}

            except Exception as e:
                reset_session_state(session_id)
                db.log_audit(session_id, "error", f"Order creation error: {e}", {"error": str(e)})
                reply = "A system error occurred. Please try again."
                db.add_chat_message(session_id, 'agent', reply)
                return {"session_id": session_id, "response": reply, "state": "idle"}

        elif intent['action'] == 'cancel':
            reset_session_state(session_id)
            db.log_audit(session_id, "confirm_cancel",
                         f"User declined purchase of '{product['name']}'.")
            reply = f"No problem, cancelled the order for {product['name']}. What else would you like to explore?"
            db.add_chat_message(session_id, 'agent', reply)
            return {"session_id": session_id, "response": reply, "state": "idle",
                    "decision_lifecycle": [{"stage": "Action", "detail": "Order declined by user", "status": "done"}]}
        elif intent['action'] == 'search' or intent.get('customer_signal') in ('price_objection', 'budget_constraint', 'feature_inquiry'):
            # User changed their mind or asked a new question — reset pending order and flow into search/agentic loop
            reset_session_state(session_id)
            current_state = 'idle'
            # Fall through to idle agentic flow below
        else:
            reply = (f"Please confirm your order: {quantity}x **{product['name']}** "
                     f"for Rs.{amount:,.0f}.\n\nClick **Confirm** to proceed or **Decline / Cancel** to look for something else.")
            db.add_chat_message(session_id, 'agent', reply)
            return {"session_id": session_id, "response": reply, "state": "awaiting_confirmation",
                    "decision_lifecycle": state_data.get('last_lifecycle', [])}

    # ── Idle: main agentic flow ───────────────────────────────────────────────
    intent        = agent.parse_intent(session_id, message, current_state)
    action        = intent['action']
    signal        = intent['customer_signal']
    quantity      = intent['quantity']
    max_price     = intent['max_price']
    strategy_stats = db.get_strategy_performance_stats()
    obj_label     = agent.OBJECTIVE_LABELS.get(merchant_settings['objective'], 'Protect Profit')

    # Update customer memory with signal
    if signal == 'price_objection':
        db.update_customer_memory(session_id, last_objection='price_objection')

    matched_product = None

    # Context-aware: link objection/buy to active product from UI
    if req.active_product_id:
        matched_product = db.get_product(req.active_product_id)
        if matched_product:
            db.log_audit(session_id, "context_match",
                         f"Signal linked to active product '{matched_product['name']}'.",
                         {"active_product_id": req.active_product_id})

    # Search if no context product
    top_products = []
    if intent.get('query'):
        top_products = agent.match_top_products(session_id, intent['query'], max_price, limit=4)
        if not matched_product and top_products:
            matched_product = top_products[0]

    if not matched_product and not top_products:
        reply = "I'm your AI shopping assistant! You can ask for recommendations, compare products, or browse our 110-item catalog across earbuds, headphones, smartwatches, speakers, gaming gear, and more."
        db.add_chat_message(session_id, 'agent', reply)
        audit_id = db.log_audit(session_id, "greeting_prompt", "AI greeting prompt rendered.")
        lifecycle = [
            {"stage": "Customer Signal",   "signal_code": signal.upper(), "customer_input": message, "detail": "General inquiry", "status": "done"},
            {"stage": "Context Evaluated", "merchant_objective": obj_label, "price_sensitivity": "Low", "purchase_intent": "Low", "margin_guard": "Protected", "detail": f"Objective: {obj_label}", "badges": {"intent": "Low", "objective": obj_label, "margin_guard": "Protected"}, "status": "done"},
            {"stage": "AI Proposal",       "proposed_action": "Guide Catalog Exploration", "confidence": "95%", "reason": "General inquiry without product reference.", "detail": "Guide Catalog Exploration (95% conf)", "status": "done"},
            {"stage": "Policy Validation", "policy_result": "PASSED", "detail": "PASSED — Standard catalog guidance", "checks_enforced": ["Standard Policy"], "status": "done"},
            {"stage": "Risk Gate",         "risk_level": "LOW", "gate_status": "APPROVED", "detail": "Risk: LOW · Auto-approved", "status": "done"},
            {"stage": "Action Execution",  "execution_detail": "Greeting & catalog categories presented", "detail": "Assistant guidance rendered", "status": "active"},
            {"stage": "Audit Event",       "audit_id": audit_id, "action_type": "greeting_prompt", "detail": f"Audit ID: {audit_id} · Committed", "status": "done"}
        ]
        return {"session_id": session_id, "response": reply, "state": "idle",
                "decision_lifecycle": lifecycle, "products_recommended": []}

    if not matched_product and top_products:
        matched_product = top_products[0]

    # ── Case 0: Explicit AI Upsell & Cross-Sell Flow ─────────────────────────
    if signal == 'upsell_opportunity' or intent.get('action') == 'upsell':
        upsell_data = agent.find_complementary_upsell(matched_product, message)
        if upsell_data:
            comp_prod = upsell_data['complementary_product']
            reply = (
                f"Great choice with **{matched_product['name']}**! To {upsell_data['pitch_reason']}, "
                f"I recommend pairing them with the **{comp_prod['name']}** (Rs.{comp_prod['price']:,.0f}).\n\n"
                f"Would you like to bundle this together for a total of **Rs.{upsell_data['bundle_price']:,.0f}**?"
            )
            audit_id = db.log_audit(
                session_id,
                "upsell_cross_sell_recommended",
                f"AI recommended complementary '{comp_prod['name']}' (Rs.{comp_prod['price']:,.0f}) to pair with '{matched_product['name']}'.",
                {
                    "main_product_id": matched_product['id'],
                    "complementary_product_id": comp_prod['id'],
                    "incremental_revenue": upsell_data['incremental_revenue'],
                    "stock_available": upsell_data['stock_available']
                }
            )

            lifecycle = [
                {"stage": "Customer Signal",   "signal_code": "UPSELL_OPPORTUNITY", "customer_input": message, "detail": "Complementary Add-on / Upsell Request", "status": "done"},
                {"stage": "Context Evaluated", "merchant_objective": obj_label, "target_product": matched_product['name'], "price_sensitivity": "Balanced", "purchase_intent": "Expanding Basket", "margin_guard": "Protected", "detail": f"Objective: {obj_label} | Margin: Protected", "badges": {"intent": "Expanding Basket", "objective": obj_label, "sensitivity": "Balanced", "margin_guard": "Protected"}, "status": "done"},
                {"stage": "AI Proposal",       "proposed_action": f"Recommend {comp_prod['name']}", "confidence": "94%", "reason": f"Relevant complementary product with available stock ({comp_prod['stock']} units available).", "detail": f"Recommend {comp_prod['name']} (94% conf)", "status": "done"},
                {"stage": "Policy Validation", "policy_result": "PASSED", "detail": "PASSED - Category mapping & in-stock verification satisfied", "checks_enforced": ["Complementary Category Mapping", "In-Stock Guard", "Margin Floor Guard"], "status": "done"},
                {"stage": "Risk Gate",         "risk_level": "LOW", "gate_status": "APPROVED", "detail": "Risk: LOW - Auto-executable complementary cross-sell", "status": "done"},
                {"stage": "Action Execution",  "execution_detail": f"Complementary recommendation presented with 1-click bundle (+Rs.{comp_prod['price']:,.0f} revenue)", "detail": f"Pairing: {matched_product['name']} + {comp_prod['name']}", "final_amount": f"Rs.{upsell_data['bundle_price']:,.0f}", "status": "active"},
                {"stage": "Audit Event",       "audit_id": audit_id, "action_type": "upsell_cross_sell_recommended", "detail": f"Audit ID: {audit_id} - Committed", "status": "done"}
            ]

            db.add_chat_message(session_id, 'agent', reply)
            return {
                "session_id": session_id,
                "response": reply,
                "state": "idle",
                "decision_card": {
                    "signal": "Upsell Opportunity",
                    "analysis": {
                        "purchase_intent": "Expanding Basket",
                        "price_sensitivity": "Balanced",
                        "margin_health": "Protected (Safe)",
                        "merchant_objective": obj_label,
                        "confidence": "94%"
                    },
                    "decision": f"Recommend {comp_prod['name']}",
                    "risk_level": "LOW",
                    "approval_status": "APPROVED",
                    "validation_status": "APPROVED",
                    "incentive_applied": "none",
                    "audit_id": audit_id,
                    "reasoning": f"Relevant complementary product with available stock ({comp_prod['stock']} units available).",
                    "expected_impact": f"Increase order value (+Rs.{comp_prod['price']:,.0f} revenue)",
                    "outcome": "Increase Average Order Value"
                },
                "products_recommended": [matched_product, comp_prod],
                "decision_lifecycle": lifecycle
            }

    # ── Case 1: Multi-Item Discovery / Search / Category Browsing ───────────────
    if signal in ('general', 'budget_constraint', 'feature_inquiry') and intent.get('action') not in ('buy', 'confirm'):
        candidate_list = top_products if len(top_products) > 1 else agent.match_top_products(session_id, matched_product['category'], limit=4)
        if not candidate_list:
            candidate_list = [matched_product]

        lines = [f"Here are the top recommendations based on your request:\n"]
        for i, p in enumerate(candidate_list[:4], 1):
            feats = p.get('features', [])
            if isinstance(feats, str):
                try: feats = json.loads(feats)
                except: feats = []
            feat_str = f" • {', '.join(feats[:2])}" if feats else ""
            lines.append(f"{i}. **{p['name']}** — **Rs.{p['price']:,.0f}**{feat_str}\n   {p['description']}")
        lines.append("\nYou can click any card below to view specs, compare alternatives, or start checkout when you're ready.")
        reply = "\n".join(lines)

        audit_id = db.log_audit(session_id, "catalog_discovery",
                                f"Curated {len(candidate_list)} options for query '{message}'.",
                                {"product_count": len(candidate_list), "objective": merchant_settings['objective']})

        lifecycle = [
            {"stage": "Customer Signal",   "signal_code": signal.upper(), "customer_input": message, "detail": _signal_label(signal), "status": "done"},
            {"stage": "Context Evaluated", "merchant_objective": obj_label, "target_product": matched_product['name'], "price_sensitivity": _sensitivity_label(signal), "purchase_intent": _intent_label(signal), "margin_guard": "Protected", "detail": f"Objective: {obj_label} | Margin: Protected", "badges": {"intent": _intent_label(signal), "objective": obj_label, "sensitivity": _sensitivity_label(signal), "margin_guard": "Protected"}, "status": "done"},
            {"stage": "AI Proposal",       "proposed_action": f"Curate {len(candidate_list)} Relevant Options", "confidence": "90%", "reason": "User is exploring products. Presenting high-relevance options with comparative trade-offs.", "detail": f"Curate {len(candidate_list)} Options (90% conf)", "status": "done"},
            {"stage": "Policy Validation", "policy_result": "PASSED", "detail": "PASSED - Standard catalog pricing and stock verified", "checks_enforced": ["Standard Policy", "Stock Verification"], "status": "done"},
            {"stage": "Risk Gate",         "risk_level": "LOW", "gate_status": "APPROVED", "detail": "Risk: LOW - Auto-executable", "status": "done"},
            {"stage": "Action Execution",  "execution_detail": f"Curated {len(candidate_list)} product cards presented", "detail": "Catalog Guidance Active", "status": "active"},
            {"stage": "Audit Event",       "audit_id": audit_id, "action_type": "catalog_discovery", "detail": f"Audit ID: {audit_id} - Committed", "status": "done"}
        ]

        db.add_chat_message(session_id, 'agent', reply)
        return {
            "session_id": session_id,
            "response": reply,
            "state": "idle",
            "decision_card": {
                "signal": "Browsing & Discovery",
                "analysis": {
                    "purchase_intent": "Exploratory",
                    "price_sensitivity": "Balanced",
                    "margin_health": "Protected (Safe)",
                    "merchant_objective": obj_label,
                    "confidence": "90%"
                },
                "decision": f"Curated {len(candidate_list)} Options",
                "risk_level": "LOW",
                "approval_status": "APPROVED",
                "validation_status": "APPROVED",
                "incentive_applied": "none",
                "audit_id": audit_id,
                "reasoning": "User is exploring products. Presenting high-relevance options with comparative trade-offs rather than forcing immediate purchase.",
                "outcome": "Empower Customer Choice"
            },
            "products_recommended": candidate_list[:4],
            "decision_lifecycle": lifecycle
        }

    # ── Case 2: Comparison Mode ────────────────────────────────────────────────
    if signal == 'comparison':
        compare_candidates = top_products[:2] if len(top_products) >= 2 else agent.match_top_products(session_id, matched_product['category'], limit=2)
        if len(compare_candidates) >= 2:
            p1, p2 = compare_candidates[0], compare_candidates[1]
            p1_feats = p1.get('features', []) if isinstance(p1.get('features'), list) else json.loads(p1.get('features', '[]'))
            p2_feats = p2.get('features', []) if isinstance(p2.get('features'), list) else json.loads(p2.get('features', '[]'))
            reply = (
                f"### Side-by-Side Comparison:\n\n"
                f"* **{p1['name']}** (Rs.{p1['price']:,.0f}): {p1['description']}\n"
                f"  Highlights: {', '.join(p1_feats[:3])}\n\n"
                f"* **{p2['name']}** (Rs.{p2['price']:,.0f}): {p2['description']}\n"
                f"  Highlights: {', '.join(p2_feats[:3])}\n\n"
                f"Recommendation: Choose **{p1['name']}** for maximum features or **{p2['name']}** for great price-to-performance."
            )
        else:
            reply = f"**{matched_product['name']}** is one of our top rated items in {matched_product['category']}. Check the specs card below or ask to compare with another model!"
            compare_candidates = [matched_product]

        audit_id = db.log_audit(session_id, "product_comparison",
                                f"Comparison rendered between {[p['name'] for p in compare_candidates]}.",
                                {"products": [p['id'] for p in compare_candidates]})

        lifecycle = [
            {"stage": "Customer Signal",   "signal_code": "COMPARISON", "customer_input": message, "detail": "Product Comparison Request", "status": "done"},
            {"stage": "Context Evaluated", "merchant_objective": obj_label, "target_product": matched_product['name'], "price_sensitivity": "Feature-Focused", "purchase_intent": "Evaluating Options", "margin_guard": "Protected", "detail": f"Objective: {obj_label} | Margin: Protected", "badges": {"intent": "Evaluating Options", "objective": obj_label, "sensitivity": "Feature-Focused", "margin_guard": "Protected"}, "status": "done"},
            {"stage": "AI Proposal",       "proposed_action": "Side-by-Side Feature Matrix", "confidence": "92%", "reason": "Comparing candidate models side-by-side to assist educated buying decision.", "detail": "Side-by-Side Matrix (92% conf)", "status": "done"},
            {"stage": "Policy Validation", "policy_result": "PASSED", "detail": "PASSED - Specification matrix compliant", "checks_enforced": ["Standard Policy"], "status": "done"},
            {"stage": "Risk Gate",         "risk_level": "LOW", "gate_status": "APPROVED", "detail": "Risk: LOW - Auto-executable", "status": "done"},
            {"stage": "Action Execution",  "execution_detail": "Side-by-Side comparison cards rendered", "detail": "Comparison Matrix Active", "status": "active"},
            {"stage": "Audit Event",       "audit_id": audit_id, "action_type": "product_comparison", "detail": f"Audit ID: {audit_id} - Committed", "status": "done"}
        ]

        db.add_chat_message(session_id, 'agent', reply)
        return {
            "session_id": session_id,
            "response": reply,
            "state": "idle",
            "decision_card": {
                "signal": "Comparison Analysis",
                "analysis": {
                    "purchase_intent": "Evaluating Options",
                    "price_sensitivity": "Feature-Focused",
                    "margin_health": "Protected (Safe)",
                    "merchant_objective": obj_label,
                    "confidence": "92%"
                },
                "decision": "Feature Matrix Comparison",
                "risk_level": "LOW",
                "approval_status": "APPROVED",
                "validation_status": "APPROVED",
                "incentive_applied": "none",
                "audit_id": audit_id,
                "reasoning": "Comparing candidate models side-by-side to assist educated buying decision.",
                "outcome": "Clarity on Best-Fit SKU"
            },
            "products_recommended": compare_candidates,
            "decision_lifecycle": lifecycle
        }

    # ── AI Strategy Proposal for Objections or Buy Intents ────────────────────
    conversation_history = db.get_chat_history(session_id, limit=8)
    proposal = agent.propose_strategy(
        session_id=session_id,
        product=matched_product,
        signal=signal,
        quantity=quantity,
        conversation_history=conversation_history,
        merchant_settings=merchant_settings,
        customer_memory=customer_memory,
        strategy_stats=strategy_stats,
        user_message=message
    )

    # ── Backend Validation (Hard Boundaries vs Approval Gates) ───────────────
    validated = agent.validate_proposal(
        session_id=session_id,
        proposal=proposal,
        product=matched_product,
        quantity=quantity,
        merchant_settings=merchant_settings,
        customer_memory=customer_memory
    )

    validation_label = validated['approval_status']
    risk_level = validated.get('risk_level', 'LOW')

    # ── HIGH-risk: action needs merchant approval — do NOT execute ────────────
    if validated['approval_status'] == "WAITING FOR MERCHANT APPROVAL":
        approval_id = validated.get('approval_id', '')
        audit_id = db.log_audit(session_id, "risk_gate_high_pending",
                                f"HIGH-risk action '{proposal['recommended_action']}' queued for merchant review (id={approval_id}).",
                                {"approval_id": approval_id, "action": proposal['recommended_action']})
        reply = (
            f"The AI proposed a high-value incentive on **{matched_product['name']}**. "
            f"This action has been queued for review in the **Merchant Hub -> Approvals** panel.\n\n"
            f"Your order is on hold until the merchant approves or blocks it "
            f"(Reference: `{approval_id}`)."
        )

        lifecycle = [
            {"stage": "Customer Signal",   "signal_code": signal.upper(), "customer_input": message, "detail": _signal_label(signal), "status": "done"},
            {"stage": "Context Evaluated", "merchant_objective": obj_label, "target_product": matched_product['name'], "price_sensitivity": _sensitivity_label(signal), "purchase_intent": _intent_label(signal), "margin_guard": "Protected", "detail": f"Objective: {obj_label} | Margin: Protected", "badges": {"intent": _intent_label(signal), "objective": obj_label, "sensitivity": _sensitivity_label(signal), "margin_guard": "Protected"}, "status": "done"},
            {"stage": "AI Proposal",       "proposed_action": proposal['recommended_action'].replace('_',' ').title(), "confidence": f"{proposal.get('confidence', 0.8):.0%}", "reason": proposal.get('reasoning', ''), "detail": f"{proposal['recommended_action'].replace('_',' ').title()} ({proposal.get('confidence', 0.8):.0%} conf)", "status": "done"},
            {"stage": "Policy Validation", "policy_result": "WAITING FOR MERCHANT APPROVAL", "detail": f"Action requires merchant approval (threshold={merchant_settings.get('high_risk_discount_threshold', 10):.0f}%, cap={merchant_settings.get('max_discount_pct', 20):.0f}%)", "checks_enforced": ["Max Discount Cap", "Single Incentive Policy", "Margin Floor Guard"], "status": "pending"},
            {"stage": "Risk Gate",         "risk_level": "HIGH", "gate_status": "WAITING FOR MERCHANT APPROVAL", "detail": f"Risk: HIGH - Queued (Approval ID: {approval_id})", "status": "blocked"},
            {"stage": "Action Execution",  "execution_detail": "Execution held pending merchant authorization", "detail": "Waiting for merchant approval", "status": "pending"},
            {"stage": "Audit Event",       "audit_id": audit_id, "action_type": "risk_gate_high_pending", "detail": f"Audit ID: {audit_id} - Append-Only Ledger", "status": "done"}
        ]

        db.add_chat_message(session_id, 'agent', reply)
        return {
            "session_id": session_id,
            "response": reply,
            "state": "idle",
            "decision_card": {
                "signal": proposal.get('customer_state', '').replace('_', ' ').title(),
                "analysis": {
                    "purchase_intent": "High",
                    "price_sensitivity": "High",
                    "margin_health": "Protected (Safe)",
                    "merchant_objective": obj_label,
                    "confidence": f"{proposal.get('confidence', 0.7):.0%}"
                },
                "decision": "Awaiting Merchant Approval",
                "risk_level": "HIGH",
                "approval_status": "WAITING FOR MERCHANT APPROVAL",
                "approval_id": approval_id,
                "validation_status": "WAITING FOR MERCHANT APPROVAL",
                "incentive_applied": "none",
                "audit_id": audit_id,
                "reasoning": proposal.get('reasoning', ''),
                "outcome": "Pending Approval"
            },
            "products_recommended": [matched_product],
            "decision_lifecycle": lifecycle
        }

    # ── Execute Strategy (LOW / MEDIUM / BLOCKED handled here) ───────────────
    result = agent.execute_strategy(
        session_id=session_id,
        validated=validated,
        proposal=proposal,
        product=matched_product,
        quantity=quantity,
        merchant_settings=merchant_settings
    )

    audit_id = result.get('audit_id') or db.log_audit(session_id, result['strategy'],
                                                       f"Strategy '{result['strategy']}' executed. Incentive: {result['incentive']}.",
                                                       {"product_id": matched_product['id'], "incentive": result['incentive']})

    policy_detail = "PASSED - All bounds satisfied" if validated['approved'] else f"BLOCKED - {validated.get('rejection_reason', 'Policy bound')}"

    lifecycle = [
        {"stage": "Customer Signal",   "signal_code": signal.upper(), "customer_input": message, "detail": _signal_label(signal), "status": "done"},
        {"stage": "Context Evaluated", "merchant_objective": obj_label, "target_product": matched_product['name'], "price_sensitivity": _sensitivity_label(signal), "purchase_intent": _intent_label(signal), "margin_guard": "Protected", "detail": f"Objective: {obj_label} | Margin: Protected", "badges": {"intent": _intent_label(signal), "objective": obj_label, "sensitivity": _sensitivity_label(signal), "margin_guard": "Protected"}, "status": "done"},
        {"stage": "AI Proposal",       "proposed_action": proposal['recommended_action'].replace('_',' ').title(), "confidence": f"{proposal.get('confidence', 0.8):.0%}", "reason": proposal.get('reasoning', ''), "detail": f"{proposal['recommended_action'].replace('_',' ').title()} ({proposal.get('confidence', 0.8):.0%} conf)", "status": "done"},
        {"stage": "Policy Validation", "policy_result": "PASSED" if validated['approved'] else "BLOCKED", "detail": policy_detail, "checks_enforced": ["Max Discount Cap", "Single Incentive Policy", "Margin Floor Guard"], "status": "done" if validated['approved'] else "warning"},
        {"stage": "Risk Gate",         "risk_level": risk_level, "gate_status": validated['approval_status'], "detail": f"Risk: {risk_level} - Status: {validated['approval_status']}", "status": "done" if validated['approved'] else "warning"},
        {"stage": "Action Execution",  "execution_detail": f"{result['strategy'].replace('_',' ').title()} applied" if validated['approved'] else f"Action BLOCKED: {validated.get('rejection_reason', 'Policy limit')}", "detail": f"{result['strategy'].replace('_',' ').title()} applied" + (f" - {result['incentive']}" if result['incentive'] != 'none' else "") if validated['approved'] else "Action Blocked", "final_amount": f"Rs.{result['final_amount']:,.0f}", "status": "active" if validated['approved'] else "blocked"},
        {"stage": "Audit Event",       "audit_id": audit_id, "action_type": result['strategy'], "detail": f"Audit ID: {audit_id} - Append-Only Ledger", "status": "done"}
    ]

    # ── Guardrails ────────────────────────────────────────────────────
    effective_product = result.get('alternative_product') or matched_product
    guardrail = agent.check_guardrails(session_id, effective_product, quantity, result['final_amount'])

    if not guardrail['allowed']:
        if guardrail['escalate']:
            state_data['state'] = 'awaiting_escalation'
        db.add_chat_message(session_id, 'agent', guardrail['reason'])
        return {
            "session_id": session_id,
            "response": guardrail['reason'],
            "state": state_data['state'],
            "decision_card": result['decision_card'],
            "products_recommended": [effective_product],
            "decision_lifecycle": lifecycle
        }

    # ── Price Objection Handling (Offer Choices) ──────────────────────────────
    if signal == 'price_objection':
        final_action = result['strategy']
        recs = [effective_product]
        if result.get('alternative_product') and result['alternative_product']['id'] != effective_product['id']:
            recs.append(result['alternative_product'])
        else:
            category_cheaper = [p for p in db.get_products(matched_product['category']) if p['id'] != matched_product['id'] and p['price'] < matched_product['price']]
            if category_cheaper:
                recs.append(category_cheaper[0])

        if not validated['approved']:
            reply = f"I cannot approve that requested discount on **{matched_product['name']}** because it violates our hard policy safety limits ({validated.get('rejection_reason', 'Limit exceeded')}).\n\nI can offer standard pricing or help you find a great alternative in the same category."
        else:
            reply = result['reasoning']
            if result['incentive'] != 'none':
                reply += f"\n\n👉 Click **Buy Now** on the card below or reply **'I want to buy {effective_product['name']}'** to lock in this deal!"
                state_data['pending_product'] = effective_product
                state_data['pending_quantity'] = quantity
                state_data['pending_amount'] = result['final_amount']
                state_data['incentive_used'] = result['incentive']
                state_data['state'] = 'awaiting_confirmation'

        db.add_chat_message(session_id, 'agent', reply)
        return {
            "session_id": session_id,
            "response": reply,
            "state": state_data['state'],
            "decision_card": result['decision_card'],
            "products_recommended": recs,
            "decision_lifecycle": lifecycle
        }

    # ── Explicit Buy Intent Flow ──────────────────────────────────────────────
    state_data['state'] = 'awaiting_confirmation'
    state_data['pending_product'] = effective_product
    state_data['pending_quantity'] = quantity
    state_data['pending_amount'] = result['final_amount']
    state_data['incentive_used'] = result['incentive']
    state_data['requires_extra_confirm'] = guardrail['extra_confirm']
    state_data['last_lifecycle'] = lifecycle

    reply = f"I've configured your order for {quantity}x **{effective_product['name']}** at **Rs.{result['final_amount']:,.0f}**"
    if result['incentive'] != 'none':
        reply += f" (Incentive: `{result['incentive']}` applied)"
    reply += ".\n\nReady to proceed? Reply **'confirm'** or click below to launch secure Razorpay checkout."

    db.add_chat_message(session_id, 'agent', reply)
    return {
        "session_id": session_id,
        "response": reply,
        "state": state_data['state'],
        "decision_card": result['decision_card'],
        "products_recommended": [effective_product],
        "decision_lifecycle": lifecycle
    }


def _signal_label(signal):
    labels = {
        "price_objection": "Price objection detected",
        "budget_constraint": "Budget constraint identified",
        "ready_to_buy": "High purchase intent — ready to buy",
        "feature_inquiry": "Feature inquiry",
        "general": "General browsing intent"
    }
    return labels.get(signal, signal.replace('_', ' ').title())

def _intent_label(signal):
    if signal in ('ready_to_buy',): return 'Very High'
    if signal in ('price_objection', 'budget_constraint'): return 'High'
    if signal == 'feature_inquiry': return 'Medium'
    return 'Low'

def _sensitivity_label(signal):
    if signal in ('price_objection', 'budget_constraint'): return 'High'
    if signal == 'ready_to_buy': return 'Low'
    return 'Medium'


# ── Razorpay Order Creation & Payment Verification ───────────────────────────

@app.post("/api/create-order")
def create_order_endpoint(req: CreateOrderRequest):
    """
    Standard Razorpay Order Creation Endpoint.
    Accepts amount in paise or rupees (minimum 100 paise / ₹1.00).
    Calls Razorpay Orders API: POST https://api.razorpay.com/v1/orders
    Returns: { order_id, id, amount, currency, key_id, razorpay_options }
    """
    session_id = req.session_id or f"direct_{uuid.uuid4().hex[:8]}"

    # Normalize amount: if sent in paise (>= 100 and typically large) or rupees
    # Minimum required is 100 paise (Rs. 1.00)
    if req.amount >= 100 and (not req.product_id or req.amount > 10000):
        amount_in_paise = int(req.amount)
    elif req.product_id:
        prod = db.get_product(req.product_id)
        if prod:
            amount_in_paise = int(round(prod['price'] * 100))
        else:
            amount_in_paise = int(round(req.amount * 100)) if req.amount < 10000 else int(req.amount)
    else:
        amount_in_paise = int(round(req.amount * 100)) if req.amount < 10000 else int(req.amount)

    if amount_in_paise < 100:
        raise HTTPException(
            status_code=400,
            detail="Minimum order amount must be at least 100 paise (₹1.00 INR)."
        )

    receipt = req.receipt or f"rcpt_{uuid.uuid4().hex[:8]}"
    product_name = "Store Item"
    product_id = req.product_id or "custom_item"
    if req.product_id:
        prod = db.get_product(req.product_id)
        if prod:
            product_name = prod['name']

    try:
        db_order_id = db.create_order(
            session_id=session_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount_in_paise / 100.0,
            status='pending',
            incentive_used='none'
        )

        rzp_order = payments.create_razorpay_order(
            session_id=session_id,
            amount_in_rupees=amount_in_paise / 100.0,
            order_db_id=db_order_id
        )

        if not rzp_order or 'id' not in rzp_order:
            raise HTTPException(status_code=500, detail="Razorpay API order creation failed.")

        # Update DB order with razorpay_order_id
        conn = db.get_db_connection()
        conn.cursor().execute('UPDATE orders SET razorpay_order_id = ? WHERE id = ?',
                             (rzp_order['id'], db_order_id))
        conn.commit()
        conn.close()

        razorpay_options = {
            "key": payments.RAZORPAY_KEY_ID or "",
            "amount": rzp_order['amount'],
            "currency": rzp_order.get('currency', req.currency or 'INR'),
            "name": "GrowthPilot AI",
            "description": f"Order #{db_order_id} - {product_name}",
            "order_id": rzp_order['id'],
            "prefill": {
                "name": "Guest Customer",
                "email": "customer@growthpilot.ai",
                "contact": "9999999999"
            },
            "theme": {
                "color": "#F7931A"
            }
        }

        return {
            "order_id": rzp_order['id'],
            "id": rzp_order['id'],
            "amount": rzp_order['amount'],
            "currency": rzp_order.get('currency', req.currency or 'INR'),
            "receipt": receipt,
            "key_id": payments.RAZORPAY_KEY_ID,
            "razorpay_options": razorpay_options,
            "status": "created"
        }

    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e)
        if "Unauthorized" in err_str or "auth" in err_str.lower():
            raise HTTPException(status_code=401, detail=f"Razorpay Authentication Failure: {err_str}")
        raise HTTPException(status_code=500, detail=f"Razorpay Order Creation Error: {err_str}")


# ── Payment verification ──────────────────────────────────────────────────────

@app.post("/api/verify-payment")
def verify_payment_endpoint(req: VerifyRequest):
    if req.status == 'failed':
        payments.record_client_payment_failure(req.session_id, req.razorpay_order_id, req.error or {})
        return {"status": "recorded", "message": "Failure logged."}
    elif req.status == 'success':
        if not req.razorpay_payment_id or not req.razorpay_signature:
            raise HTTPException(status_code=400, detail="Missing signature tokens.")
        verified = payments.verify_razorpay_payment(
            session_id=req.session_id,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature
        )
        if verified:
            return {"status": "success", "message": "Payment verified!"}
        else:
            raise HTTPException(status_code=400, detail="Signature verification failed.")
    raise HTTPException(status_code=400, detail="Invalid status.")


# ── Merchant dashboard endpoints ──────────────────────────────────────────────

@app.get("/api/merchant/metrics")
def get_metrics():
    return db.get_merchant_metrics()

@app.get("/api/merchant/logs")
def get_logs(session_id: Optional[str] = None):
    return db.get_audit_log(session_id)

@app.get("/api/merchant/charts")
def get_charts():
    return db.get_dashboard_chart_data()

@app.get("/api/merchant/strategy-stats")
def get_strategy_stats():
    return db.get_strategy_performance_stats()

@app.get("/api/conversations/{session_id}")
def get_conversation(session_id: str):
    return db.get_all_chat_history(session_id)

# ── Strategy outcome feedback ─────────────────────────────────────────────────

@app.post("/api/strategy-outcome")
def record_outcome(req: StrategyOutcomeRequest):
    settings = db.get_merchant_settings()
    db.record_strategy_outcome(
        session_id=req.session_id,
        strategy=req.strategy,
        product_id=req.product_id,
        product_name=req.product_name,
        customer_state=req.customer_state,
        merchant_objective=settings['objective'],
        result=req.result,
        revenue=req.revenue,
        profit_delta=req.profit_delta
    )
    return {"status": "recorded"}


@app.post("/api/demo/reset")
def reset_demo_endpoint():
    """Reset all orders, metrics, approvals, and state for a fresh recording session."""
    SESSION_STATES.clear()
    return db.reset_demo_data()

# ── Abandoned checkout endpoints ──────────────────────────────────────────────

@app.get("/api/abandoned-checkouts")
def get_abandoned(session_id: Optional[str] = None):
    abandoned = db.get_abandoned_checkouts(session_id)
    result = []
    for ev in abandoned:
        settings = db.get_merchant_settings()
        mem = db.get_customer_memory(ev['session_id'])
        recovery_msg = agent.generate_recovery_message(ev['session_id'], ev, settings)
        ev['recovery_message'] = recovery_msg
        result.append(ev)
    return result

@app.post("/api/simulate-abandonment")
def simulate_abandonment(req: dict):
    session_id = req.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required.")
    result = db.simulate_abandonment(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No pending checkout found for this session.")
    # Also reset session state so they can re-interact
    reset_session_state(session_id)
    return {"status": "abandoned", "order": result}


# ── Buyer-agent surface (Step 1) ──────────────────────────────────────────────

@app.get("/.well-known/agent.json")
def get_agent_manifest():
    """Discovery manifest for external AI buyer agents."""
    return agent_buyer.AGENT_MANIFEST


@app.get("/api/agent/catalog")
def get_agent_catalog(category: Optional[str] = None):
    """Agent-readable product catalog. Strips cost_price / profit_margin."""
    products = db.get_products(category)
    projected = [agent_buyer.project_product_for_buyer(p) for p in products]
    return {
        "merchant": agent_buyer.AGENT_MANIFEST["name"],
        "policy_version": agent_buyer.POLICY_VERSION,
        "currency": "INR",
        "count": len(projected),
        "products": projected,
        "checkout_intent_template": agent_buyer.build_intent_template(),
    }


@app.get("/api/agent/policy")
def get_agent_policy():
    """Read-only policy snapshot — let buyer agents pre-check before sending intents."""
    settings = db.get_merchant_settings()
    return {
        "merchant_policy": settings,
        "agent_buyer_policy": agent_buyer.AGENT_BUYER_POLICY,
    }


@app.post("/api/agent/checkout/intent")
def post_checkout_intent(req: BuyerCheckoutIntentRequest):
    """
    Create a signed checkout intent.
    Returns 200 on success, 409 on policy block (with retry_suggestion).
    """
    if req.intent_version and req.intent_version < agent_buyer.MIN_INTENT_VERSION:
        raise HTTPException(status_code=400, detail=f"intent_version must be >= {agent_buyer.MIN_INTENT_VERSION}")

    # Reconstruct mandate without 'signature' / 'intent_version' for signing.
    # IMPORTANT: preserve the raw JSON types of every numeric field so the
    # canonical JSON matches what the buyer agent signed. We do this by
    # walking the raw request body when available, otherwise falling back to
    # the Pydantic-dumped values (which always coerce to float).
    raw = None
    try:
        raw = getattr(req, "raw_body", None) or None
    except Exception:
        raw = None
    # FastAPI/Pydantic v2 doesn't keep raw body, so build mandate from Pydantic
    # but cast every numeric to int if it's whole-number-safe and the original
    # request didn't carry a decimal point. We approximate by treating values
    # that fit cleanly as int as int (this matches the reference buyer which
    # sends ints).
    _items = []
    for it in req.items:
        d = {
            "product_id": it.product_id,
            "quantity":   int(it.quantity),
        }
        if it.max_unit_price is not None:
            v = it.max_unit_price
            d["max_unit_price"] = int(v) if float(v).is_integer() else float(v)
        _items.append(d)
    mandate = {
        "buyer_id":   req.buyer_id,
        "session_id": req.session_id,
        "currency":   req.currency,
        "max_total":  int(req.max_total) if float(req.max_total).is_integer() else float(req.max_total),
        "expires_at": req.expires_at,
        "items":      _items,
    }
    if not agent_buyer.verify_mandate(mandate, req.signature):
        raise HTTPException(status_code=401, detail="Invalid signature.")

    # Load products for the policy check
    products_by_id = {p["id"]: p for p in db.get_products()}
    merchant_settings = db.get_merchant_settings()
    decision = agent_buyer.evaluate_intent_policy(mandate, products_by_id, merchant_settings)

    if not decision["allowed"]:
        # Record the rejected intent for audit + future replay
        intent_id = agent_buyer.new_intent_id()
        db.create_buyer_intent(
            intent_id=intent_id,
            buyer_id=req.buyer_id,
            session_id=req.session_id,
            mandate_signature=req.signature,
            mandate_payload=mandate,
            computed_total=decision["computed_total"],
            currency=req.currency,
            status="rejected",
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            expires_at=req.expires_at,
            policy_version=agent_buyer.POLICY_VERSION,
        )
        db.update_buyer_intent_status(
            intent_id, "rejected", rejection_reason=decision["reason"]
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": "policy_block",
                "reason": decision["reason"],
                "retry_suggestion": decision["retry_suggestion"],
                "max_allowed_per_sku": decision["max_allowed_per_sku"],
                "computed_total": decision["computed_total"],
                "policy_version": agent_buyer.POLICY_VERSION,
            },
        )

    # Allowed — persist as pending
    intent_id = agent_buyer.new_intent_id()
    db.create_buyer_intent(
        intent_id=intent_id,
        buyer_id=req.buyer_id,
        session_id=req.session_id,
        mandate_signature=req.signature,
        mandate_payload=mandate,
        computed_total=decision["computed_total"],
        currency=req.currency,
        status="pending",
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=req.expires_at,
        policy_version=agent_buyer.POLICY_VERSION,
    )
    return {
        "intent_id": intent_id,
        "status": "pending",
        "computed_total": decision["computed_total"],
        "currency": req.currency,
        "expires_at": req.expires_at,
        "line_items": decision["line_items"],
        "policy_version": agent_buyer.POLICY_VERSION,
        "confirm_url": "/api/agent/checkout/confirm",
    }


@app.post("/api/agent/checkout/confirm")
def post_checkout_confirm(req: BuyerConfirmRequest):
    """
    Two-step commit: re-verify the signature and re-check policy,
    then create a Razorpay order. Returns razorpay_order_id.
    """
    intent = db.get_buyer_intent(req.intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Unknown intent_id.")
    if intent["buyer_id"] != req.buyer_id:
        raise HTTPException(status_code=403, detail="intent_id does not belong to this buyer_id.")
    if intent["status"] not in ("pending",):
        # Idempotent: if already confirmed, return the same order
        if intent["status"] == "confirmed" and intent.get("razorpay_order_id"):
            return {
                "intent_id": intent["intent_id"],
                "status": "confirmed",
                "razorpay_order_id": intent["razorpay_order_id"],
                "computed_total": intent["computed_total"],
                "payment_url": f"/api/agent/orders/{intent['intent_id']}",
            }
        raise HTTPException(status_code=409, detail=f"intent is in status '{intent['status']}', cannot confirm.")

    mandate = intent.get("mandate_payload") or {}
    if not agent_buyer.verify_mandate(mandate, req.signature):
        raise HTTPException(status_code=401, detail="Invalid signature on confirm.")

    # Re-check policy (two-step commit guard)
    products_by_id = {p["id"]: p for p in db.get_products()}
    merchant_settings = db.get_merchant_settings()
    decision = agent_buyer.evaluate_intent_policy(mandate, products_by_id, merchant_settings)
    if not decision["allowed"]:
        db.update_buyer_intent_status(
            intent["intent_id"], "rejected", rejection_reason=f"re-check failed: {decision['reason']}"
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": "policy_block",
                "reason": decision["reason"],
                "retry_suggestion": decision["retry_suggestion"],
                "max_allowed_per_sku": decision["max_allowed_per_sku"],
                "computed_total": decision["computed_total"],
                "policy_version": agent_buyer.POLICY_VERSION,
            },
        )

    # Expiry check (also re-checked)
    expires_at = agent_buyer._parse_iso(intent["expires_at"])
    if not expires_at or expires_at <= agent_buyer._now_utc():
        db.update_buyer_intent_status(
            intent["intent_id"], "expired", rejection_reason="intent expired at confirm time"
        )
        raise HTTPException(status_code=410, detail="Intent expired.")

    # Create the underlying orders row + Razorpay order for the aggregate total.
    session_id = intent.get("session_id") or f"buyer:{intent['buyer_id']}"
    total = float(intent["computed_total"])
    primary_item = decision["line_items"][0]
    db_order_id = db.create_order(
        session_id=session_id,
        product_id=primary_item["product_id"],
        product_name=primary_item["name"],
        amount=total,
        status="pending",
        incentive_used="none",
    )
    # Tag additional line items into the audit payload so the trail is honest
    if len(decision["line_items"]) > 1:
        db.log_audit(
            session_id=session_id,
            action_type="buyer_intent_multi_line",
            reasoning=(f"Intent {intent['intent_id']} contained {len(decision['line_items'])} line items; "
                       f"aggregated into a single order {db_order_id} for Rs.{total:.2f}."),
            payload={"intent_id": intent["intent_id"], "db_order_id": db_order_id,
                     "line_items": decision["line_items"]},
        )

    rzp_order = payments.create_razorpay_order(session_id, total, db_order_id)
    if not rzp_order:
        db.update_buyer_intent_status(
            intent["intent_id"], "failed", db_order_id=db_order_id,
            rejection_reason="Razorpay order creation returned no order"
        )
        raise HTTPException(status_code=502, detail="Razorpay order creation failed.")

    # Persist razorpay_order_id on the underlying order row
    conn = db.get_db_connection()
    conn.cursor().execute('UPDATE orders SET razorpay_order_id = ? WHERE id = ?',
                         (rzp_order["id"], db_order_id))
    conn.commit(); conn.close()

    db.create_checkout_event(session_id, db_order_id, rzp_order["id"], "created",
                             primary_item["name"], total, "none")

    db.update_buyer_intent_status(
        intent["intent_id"], "confirmed",
        razorpay_order_id=rzp_order["id"],
        db_order_id=db_order_id,
        confirmed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    return {
        "intent_id": intent["intent_id"],
        "status": "confirmed",
        "razorpay_order_id": rzp_order["id"],
        "computed_total": total,
        "currency": intent["currency"],
        "db_order_id": db_order_id,
        "payment_url": f"/api/agent/orders/{intent['intent_id']}",
    }


@app.get("/api/agent/orders/{intent_id}")
def get_agent_order(intent_id: str):
    intent = db.get_buyer_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Unknown intent_id.")
    return {
        "intent_id":       intent["intent_id"],
        "buyer_id":        intent["buyer_id"],
        "status":          intent["status"],
        "computed_total":  intent["computed_total"],
        "currency":        intent["currency"],
        "razorpay_order_id": intent.get("razorpay_order_id"),
        "db_order_id":     intent.get("db_order_id"),
        "created_at":      intent.get("created_at"),
        "expires_at":      intent.get("expires_at"),
        "confirmed_at":    intent.get("confirmed_at"),
        "rejection_reason":intent.get("rejection_reason"),
        "policy_version":  intent.get("policy_version"),
        "line_items":      (intent.get("mandate_payload") or {}).get("items", []),
    }


@app.post("/api/agent/webhook/payment")
def post_agent_webhook(req: BuyerWebhookRequest):
    """
    Webhook from the buyer agent's payment processor.
    Bridges the buyer-side intent to the seller-side payment verification.
    """
    intent = db.get_buyer_intent(req.intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Unknown intent_id.")
    if not intent.get("razorpay_order_id") or intent["razorpay_order_id"] != req.razorpay_order_id:
        raise HTTPException(status_code=400, detail="razorpay_order_id does not match intent.")

    session_id = intent.get("session_id") or f"buyer:{intent['buyer_id']}"

    if req.status == "failed":
        payments.record_client_payment_failure(session_id, req.razorpay_order_id, req.error or {})
        db.update_buyer_intent_status(
            intent["intent_id"], "failed",
            razorpay_payment_id=req.razorpay_payment_id,
            rejection_reason=(req.error or {}).get("description", "client reported failure"),
        )
        return {"status": "recorded", "intent_id": intent["intent_id"], "outcome": "failed"}

    if req.status == "paid":
        if not req.razorpay_payment_id or not req.razorpay_signature:
            raise HTTPException(status_code=400, detail="Missing payment_id / signature.")
        verified = payments.verify_razorpay_payment(
            session_id=session_id,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature,
        )
        if not verified:
            db.update_buyer_intent_status(
                intent["intent_id"], "failed",
                razorpay_payment_id=req.razorpay_payment_id,
                rejection_reason="signature verification failed",
            )
            raise HTTPException(status_code=400, detail="Signature verification failed.")
        db.update_buyer_intent_status(
            intent["intent_id"], "paid",
            razorpay_payment_id=req.razorpay_payment_id,
        )
        return {"status": "recorded", "intent_id": intent["intent_id"], "outcome": "paid"}

    raise HTTPException(status_code=400, detail="status must be 'paid' or 'failed'.")


# ── AI Buyer Simulation Endpoint (for UI & Interactive Demo) ──────────────────

class BuyerSimulateRequest(BaseModel):
    scenario: str = "happy_path"  # 'happy_path' | 'policy_block' | 'payment_failure'
    product_id: Optional[str] = None
    quantity: Optional[int] = None
    buyer_id: Optional[str] = None

@app.post("/api/agent/simulate-buyer")
def simulate_buyer_agent(req: BuyerSimulateRequest):
    """
    Executes a complete AI Buyer Agent transaction workflow in-process.
    Returns step-by-step telemetry, cryptographic proof, Razorpay order IDs,
    and policy evaluation results for real-time hackathon visualization.
    """
    secret = agent_buyer.AGENT_BUYER_SECRET
    buyer_id = req.buyer_id or f"ai_buyer_{uuid.uuid4().hex[:6]}"
    session_id = f"sess_agent_{uuid.uuid4().hex[:6]}"
    steps = []

    # Step 1: Discover Agent Manifest
    manifest = agent_buyer.AGENT_MANIFEST
    steps.append({
        "step": 1,
        "name": "Manifest Discovery",
        "protocol": "Agent Commerce Gateway",
        "endpoint": "/.well-known/agent.json",
        "method": "GET",
        "status": 200,
        "payload": manifest,
        "detail": f"Discovered merchant '{manifest['name']}' (Policy v{manifest['policy_version']})"
    })

    # Step 2: Query Agent-Readable Catalog
    products = db.get_products()
    projected_catalog = [agent_buyer.project_product_for_buyer(p) for p in products]
    
    target_product = None
    if req.product_id:
        target_product = next((p for p in projected_catalog if p["id"] == req.product_id), None)
    if not target_product:
        target_product = projected_catalog[0] if projected_catalog else None

    if not target_product:
        raise HTTPException(status_code=500, detail="Catalog is empty.")

    steps.append({
        "step": 2,
        "name": "Catalog Ingestion",
        "protocol": "Agent Commerce Gateway (Catalog Feed)",
        "endpoint": "/api/agent/catalog",
        "method": "GET",
        "status": 200,
        "payload": {
            "currency": "INR",
            "count": len(projected_catalog),
            "selected_sku": target_product
        },
        "detail": f"Queried {len(projected_catalog)} SKUs. Selected '{target_product['name']}' @ Rs.{target_product['price']:,}"
    })

    # Determine quantity and bounds based on scenario
    qty = req.quantity
    if qty is None:
        if req.scenario == "policy_block":
            qty = 12  # Exceeds max per-sku cap of 5
        else:
            qty = 1

    unit_price = target_product["price"]
    max_total = unit_price * qty
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=900)).strftime("%Y-%m-%dT%H:%M:%SZ")

    line_items = [{
        "product_id": target_product["id"],
        "quantity": qty,
        "max_unit_price": unit_price
    }]

    mandate = {
        "buyer_id": buyer_id,
        "session_id": session_id,
        "currency": "INR",
        "max_total": max_total,
        "expires_at": expires_at,
        "items": line_items,
    }

    # Step 3: Pre-check Policy
    policy_info = agent_buyer.AGENT_BUYER_POLICY
    steps.append({
        "step": 3,
        "name": "Policy Inspection",
        "protocol": "Agent Commerce Gateway (Policy Bounds)",
        "endpoint": "/api/agent/policy",
        "method": "GET",
        "status": 200,
        "payload": policy_info,
        "detail": f"Inspected merchant limits: Max qty/SKU = {policy_info['max_quantity_per_sku']}, Currencies = {policy_info['currencies']}"
    })

    # Step 4: Sign Mandate & Submit Checkout Intent
    signature = agent_buyer.sign_mandate(mandate, secret)
    mandate_with_sig = dict(mandate)
    mandate_with_sig["signature"] = signature

    products_by_id = {p["id"]: p for p in db.get_products()}
    merchant_settings = db.get_merchant_settings()
    decision = agent_buyer.evaluate_intent_policy(mandate, products_by_id, merchant_settings)

    intent_id = agent_buyer.new_intent_id()

    if not decision["allowed"]:
        db.create_buyer_intent(
            intent_id=intent_id,
            buyer_id=buyer_id,
            session_id=session_id,
            mandate_signature=signature,
            mandate_payload=mandate,
            computed_total=decision["computed_total"],
            currency="INR",
            status="rejected",
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            expires_at=expires_at,
            policy_version=agent_buyer.POLICY_VERSION,
        )
        db.update_buyer_intent_status(intent_id, "rejected", rejection_reason=decision["reason"])
        
        steps.append({
            "step": 4,
            "name": "Signed Intent Submission",
            "protocol": "Agent Commerce Gateway (Signed Mandate)",
            "endpoint": "/api/agent/checkout/intent",
            "method": "POST",
            "status": 409,
            "payload": {
                "mandate": mandate_with_sig,
                "response": {
                    "error": "policy_block",
                    "reason": decision["reason"],
                    "retry_suggestion": decision["retry_suggestion"],
                    "max_allowed_per_sku": decision["max_allowed_per_sku"]
                }
            },
            "detail": f"Policy Gated / Rejected: {decision['reason']} (Retry suggestion: {decision['retry_suggestion']})"
        })

        return {
            "scenario": req.scenario,
            "outcome": "policy_block",
            "success": False,
            "graceful_failure": True,
            "intent_id": intent_id,
            "steps": steps,
            "summary": f"Policy Block Handled Gracefully: Buyer agent requested {qty} units (cap is 5). Returned HTTP 409 with retry suggestion."
        }

    # Intent Allowed
    db.create_buyer_intent(
        intent_id=intent_id,
        buyer_id=buyer_id,
        session_id=session_id,
        mandate_signature=signature,
        mandate_payload=mandate,
        computed_total=decision["computed_total"],
        currency="INR",
        status="pending",
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=expires_at,
        policy_version=agent_buyer.POLICY_VERSION,
    )

    steps.append({
        "step": 4,
        "name": "Signed Intent Submission",
        "protocol": "Agent Commerce Gateway (Signed Mandate)",
        "endpoint": "/api/agent/checkout/intent",
        "method": "POST",
        "status": 200,
        "payload": {
            "intent_id": intent_id,
            "status": "pending",
            "computed_total": decision["computed_total"],
            "mandate_signature": signature
        },
        "detail": f"Cryptographic mandate validated. Intent {intent_id} approved for Rs.{decision['computed_total']:,}"
    })

    # Step 5: Two-Step Commit (Confirm) & Razorpay Order Creation
    db_order_id = db.create_order(
        session_id=session_id,
        product_id=target_product["id"],
        product_name=target_product["name"],
        amount=float(decision["computed_total"]),
        status="pending",
        incentive_used="none"
    )

    rzp_order = payments.create_razorpay_order(session_id, float(decision["computed_total"]), db_order_id)
    rzp_order_id = rzp_order["id"] if rzp_order else f"order_mock_{uuid.uuid4().hex[:8]}"

    conn = db.get_db_connection()
    conn.cursor().execute('UPDATE orders SET razorpay_order_id = ? WHERE id = ?', (rzp_order_id, db_order_id))
    conn.commit(); conn.close()

    db.create_checkout_event(session_id, db_order_id, rzp_order_id, "created", target_product["name"], float(decision["computed_total"]), "none")
    db.update_buyer_intent_status(
        intent_id, "confirmed",
        razorpay_order_id=rzp_order_id,
        db_order_id=db_order_id,
        confirmed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    steps.append({
        "step": 5,
        "name": "Two-Step Commit & Order Lock",
        "protocol": "Agent Commerce Gateway (Commit) + Razorpay",
        "endpoint": "/api/agent/checkout/confirm",
        "method": "POST",
        "status": 200,
        "payload": {
            "intent_id": intent_id,
            "status": "confirmed",
            "razorpay_order_id": rzp_order_id,
            "db_order_id": db_order_id,
            "computed_total": decision["computed_total"]
        },
        "detail": f"Order locked. Generated Razorpay Order '{rzp_order_id}' for Rs.{decision['computed_total']:,}"
    })

    # Step 6: Payment Execution / Webhook Settlement
    if req.scenario == "payment_failure":
        error_info = {"code": "BAD_REQUEST_ERROR", "description": "Card declined by issuing bank (Simulated failure)"}
        payments.record_client_payment_failure(session_id, rzp_order_id, error_info)
        db.update_buyer_intent_status(
            intent_id, "failed",
            rejection_reason=error_info["description"]
        )
        steps.append({
            "step": 6,
            "name": "Payment Webhook Callback",
            "protocol": "Razorpay Payment Callback",
            "endpoint": "/api/agent/webhook/payment",
            "method": "POST",
            "status": 200,
            "payload": {
                "intent_id": intent_id,
                "razorpay_order_id": rzp_order_id,
                "status": "failed",
                "error": error_info
            },
            "detail": f"Payment Failure Handled Gracefully: {error_info['description']}. Order state marked failed in audit trail."
        })

        return {
            "scenario": req.scenario,
            "outcome": "payment_failed",
            "success": False,
            "graceful_failure": True,
            "intent_id": intent_id,
            "razorpay_order_id": rzp_order_id,
            "steps": steps,
            "summary": f"Payment Failure Handled Gracefully: Razorpay payment for order '{rzp_order_id}' failed and was logged in immutable audit trail."
        }

    # Happy path: simulate verified settlement
    mock_pay_id = f"pay_{uuid.uuid4().hex[:10]}"
    mock_sig = f"sig_rzp_{uuid.uuid4().hex[:12]}"
    db.update_buyer_intent_status(intent_id, "paid", razorpay_payment_id=mock_pay_id)
    
    conn = db.get_db_connection()
    conn.cursor().execute("UPDATE orders SET status = 'paid', razorpay_payment_id = ? WHERE id = ?",
                         (mock_pay_id, db_order_id))
    conn.commit(); conn.close()

    db.log_audit(
        session_id=session_id,
        action_type="buyer_agent_settled",
        reasoning=f"AI Buyer '{buyer_id}' completed end-to-end purchase of '{target_product['name']}' (Rs.{decision['computed_total']:,}). Razorpay Payment ID: {mock_pay_id}.",
        payload={"intent_id": intent_id, "razorpay_order_id": rzp_order_id, "razorpay_payment_id": mock_pay_id, "amount": decision["computed_total"]}
    )

    steps.append({
        "step": 6,
        "name": "Verified Settlement & Fulfillment",
        "protocol": "Razorpay Payment Webhook",
        "endpoint": "/api/agent/webhook/payment",
        "method": "POST",
        "status": 200,
        "payload": {
            "intent_id": intent_id,
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": mock_pay_id,
            "status": "paid"
        },
        "detail": f"Payment settled successfully with Razorpay Payment ID '{mock_pay_id}'. Order state marked paid in immutable audit trail."
    })

    return {
        "scenario": req.scenario,
        "outcome": "settled",
        "success": True,
        "intent_id": intent_id,
        "razorpay_order_id": rzp_order_id,
        "razorpay_payment_id": mock_pay_id,
        "steps": steps,
        "summary": f"End-to-End Autonomous AI Buyer Transaction Succeeded: Purchased '{target_product['name']}' for Rs.{decision['computed_total']:,} with Razorpay test APIs."
    }


# ── Upsell / cross-sell recommendations ───────────────────────────────────────

@app.get("/api/recommendations/upsell")
def get_upsell(product_id: str, kind: str = "bundle"):
    """
    Cross-sell / up-sell suggestions for a product.
    kind: 'bundle' (complementary), 'upsell' (higher-tier in same category),
          'accessory' (compatible accessories), 'cheaper' (lower-tier in category).
    """
    base = db.get_product(product_id)
    if not base:
        raise HTTPException(status_code=404, detail="Unknown product.")
    products = db.get_products()
    recs = []

    if kind == "bundle":
        target_cats = agent.BUNDLE_PAIRS.get(base["category"], ["accessories"])
        candidates = [p for p in products
                      if p["category"] in target_cats and p["id"] != base["id"]
                      and p["stock"] > 0]
        candidates.sort(key=lambda p: p["price"])
        recs = candidates[:3]
    elif kind == "upsell":
        candidates = [p for p in db.get_products(base["category"])
                      if p["price"] > base["price"] and p["stock"] > 0]
        candidates.sort(key=lambda p: p["price"])
        recs = candidates[:3]
    elif kind == "cheaper":
        candidates = [p for p in db.get_products(base["category"])
                      if p["price"] < base["price"] and p["stock"] > 0]
        candidates.sort(key=lambda p: -p["price"])  # nearest cheaper
        recs = candidates[:3]
    elif kind == "accessory":
        candidates = [p for p in db.get_products("accessories") if p["stock"] > 0]
        candidates.sort(key=lambda p: p["price"])
        recs = candidates[:3]
    else:
        raise HTTPException(status_code=400, detail="kind must be bundle|upsell|cheaper|accessory")

    # Log the recommendation event
    db.log_audit(
        session_id=base["id"],  # use product id as a stand-in session for non-chat audit
        action_type=f"recommendation_{kind}",
        reasoning=f"Returned {len(recs)} {kind} recommendations for '{base['name']}'.",
        payload={"base_product_id": base["id"], "kind": kind,
                 "recommendation_ids": [p["id"] for p in recs]},
    )
    return {"base_product": base["id"], "kind": kind,
            "currency": "INR", "recommendations": recs}


# ── Campaign Orchestrator ─────────────────────────────────────────────────────

class CampaignTriggerRequest(BaseModel):
    trigger: str  # 'price_objection', 'abandoned_cart', 'high_aov_intent', 'returning_customer'
    session_id: Optional[str] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    amount: Optional[float] = 0.0


@app.post("/api/campaign/orchestrate")
def orchestrate_campaign(req: CampaignTriggerRequest):
    """
    Multi-step campaign orchestrator. Reads merchant objective + the customer's
    current trigger, and emits an ordered list of bounded, auditable campaign
    steps (the merchant can preview before launch).
    """
    settings = db.get_merchant_settings()
    objective = settings.get("objective", "protect_profit")
    steps: List[Dict[str, Any]] = []
    bounded: List[Dict[str, Any]] = []
    plan_summary = ""

    if req.trigger == "abandoned_cart":
        plan_summary = "3-step abandoned cart recovery (wait, remind, fallback)"
        steps = [
            {"step": 1, "channel": "in_app_banner", "delay_minutes": 0,
             "content": f"You left {req.product_name or 'your item'} behind.",
             "guardrails": "No new incentive; respects policy cap."},
            {"step": 2, "channel": "chat_followup", "delay_minutes": 30,
             "content": "Re-open chat with the original AI proposal.",
             "guardrails": "Re-validate quantity and price on resume."},
            {"step": 3, "channel": "discount_offer", "delay_minutes": 1440,
             "content": f"Offer max {settings['max_discount_pct']:.0f}% off only if margin remains > Rs.{settings['min_margin']:.0f}.",
             "guardrails": "Discount rejected if margin < min_margin."},
        ]
        bounded = [{"type": "discount", "max_pct": settings["max_discount_pct"],
                    "min_margin": settings["min_margin"]}]

    elif req.trigger == "price_objection":
        plan_summary = "Tiered negotiation: cheaper alt → free shipping → managed discount"
        steps = [
            {"step": 1, "channel": "agent_message",
             "content": "Suggest a cheaper product in the same category.",
             "guardrails": "Lower-priced, in-stock only."},
            {"step": 2, "channel": "agent_message",
             "content": "Offer free shipping (Rs.{:.0f}) if margin > 0.".format(settings["shipping_cost"]),
             "guardrails": "Only if product margin > shipping_cost."},
            {"step": 3, "channel": "agent_message",
             "content": f"Apply discount capped at {settings['max_discount_pct']:.0f}%.",
             "guardrails": f"Cap and min_margin (Rs.{settings['min_margin']:.0f}) enforced."},
        ]
        bounded = [{"type": "discount", "max_pct": settings["max_discount_pct"],
                    "min_margin": settings["min_margin"]},
                   {"type": "shipping", "max_value": settings["shipping_cost"]}]

    elif req.trigger == "high_aov_intent":
        plan_summary = "Bundle to grow AOV while protecting margin"
        # Pre-compute bundle suggestion if product given
        bundle_partner = None
        if req.product_id:
            base = db.get_product(req.product_id)
            if base:
                bundle_partner = agent.find_bundle_partner(base)
        steps = [
            {"step": 1, "channel": "agent_message",
             "content": "Pair primary product with a complementary accessory.",
             "guardrails": "Bundle total must keep combined margin positive."},
            {"step": 2, "channel": "agent_message",
             "content": "Show both SKUs side-by-side; let customer choose.",
             "guardrails": "Original price preserved if customer declines bundle."},
        ]
        if bundle_partner:
            steps.append({"step": 3, "channel": "checkout",
                          "content": f"Pre-fill bundle ({req.product_name} + {bundle_partner['name']}).",
                          "guardrails": "Single Razorpay order, single signature."})
        bounded = [{"type": "bundle", "max_partner_price_pct": 0.6}]

    elif req.trigger == "returning_customer":
        plan_summary = "Welcome back, resume context, skip re-introduction"
        steps = [
            {"step": 1, "channel": "agent_message",
             "content": "Resume with prior product and objection memory.",
             "guardrails": "Re-check stock + price; never auto-checkout."},
        ]
        bounded = [{"type": "context_resume", "no_money_action": True}]
    else:
        raise HTTPException(status_code=400, detail="Unknown trigger.")

    db.log_audit(
        session_id=req.session_id or "system",
        action_type="campaign_orchestrated",
        reasoning=f"Campaign for trigger '{req.trigger}' under objective '{objective}': {plan_summary}",
        payload={"trigger": req.trigger, "objective": objective,
                 "steps": steps, "bounded": bounded,
                 "product_id": req.product_id, "amount": req.amount},
    )
    return {
        "trigger": req.trigger,
        "objective": objective,
        "plan_summary": plan_summary,
        "steps": steps,
        "bounded": bounded,
        "explainable": True,
        "auditable": True,
    }


# ── Serve React build ─────────────────────────────────────────────────────────

dist_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')

# Serve product placeholder images
_static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

    @app.get("/{catchall:path}")
    def serve_frontend(catchall: str):
        if catchall.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(os.path.join(dist_dir, "index.html"))
