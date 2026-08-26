import os
import uuid
import sqlite3
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import db
import agent
import payments

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize database on startup
db.init_db()

# In-memory store for session states
# Schema per session:
# {
#     "state": "idle" | "awaiting_confirmation" | "awaiting_escalation",
#     "pending_product": dict | None,
#     "pending_quantity": int,
#     "pending_amount": float,
#     "requires_extra_confirm": bool
# }
SESSION_STATES = {}

def get_session_state(session_id):
    """Retrieve or initialize state for a session ID."""
    if session_id not in SESSION_STATES:
        SESSION_STATES[session_id] = {
            "state": "idle",
            "pending_product": None,
            "pending_quantity": 1,
            "pending_amount": 0.0,
            "requires_extra_confirm": False
        }
    return SESSION_STATES[session_id]

def reset_session_state(session_id):
    """Reset the state variables for a session to idle."""
    if session_id in SESSION_STATES:
        SESSION_STATES[session_id] = {
            "state": "idle",
            "pending_product": None,
            "pending_quantity": 1,
            "pending_amount": 0.0,
            "requires_extra_confirm": False
        }

@app.route('/')
def home():
    """Serve the main single-page chat UI."""
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Handle user chat message, process it through the state machine,
    and return the agent's textual response or payment trigger metadata.
    """
    data = request.json or {}
    message = data.get('message', '').strip()
    session_id = data.get('session_id')
    
    # Generate a session ID if not provided by client
    if not session_id:
        session_id = str(uuid.uuid4())
        
    if not message:
        return jsonify({
            "session_id": session_id,
            "response": "Please type a message.",
            "state": "idle"
        }), 400

    state_data = get_session_state(session_id)
    
    # Allow manual state resets
    if message.lower() in ['reset', 'clear', 'start over', 'reboot']:
        reset_session_state(session_id)
        db.log_audit(
            session_id=session_id,
            action_type="session_reset",
            reasoning="User explicitly requested state reset. Restored session to idle."
        )
        return jsonify({
            "session_id": session_id,
            "response": "Session reset successful. I'm ready to find products. What are you looking for?",
            "state": "idle"
        })

    # Execute state transitions
    current_state = state_data['state']
    
    # 1. State: awaiting_escalation (Order blocked by quantity guardrail)
    if current_state == 'awaiting_escalation':
        # User has to explicitly say cancel/reset to escape this state
        intent = agent.parse_intent(session_id, message, current_state)
        if intent['action'] == 'cancel':
            reset_session_state(session_id)
            return jsonify({
                "session_id": session_id,
                "response": "Escalation cleared. I've cancelled the pending item. What would you like to search for instead?",
                "state": "idle"
            })
        else:
            return jsonify({
                "session_id": session_id,
                "response": "This order is blocked because quantity exceeds the limit of 5 items. Please contact support for wholesale inquiries, or type 'cancel' to search for something else.",
                "state": "awaiting_escalation"
            })

    # Parse intent using Agent Layer (Claude + fallback)
    intent = agent.parse_intent(session_id, message, current_state)
    action = intent['action']
    
    # 2. State: awaiting_confirmation
    if current_state == 'awaiting_confirmation':
        product = state_data['pending_product']
        quantity = state_data['pending_quantity']
        amount = state_data['pending_amount']
        
        if action == 'confirm':
            # Create order in local database
            try:
                db_order_id = db.create_order(
                    session_id=session_id,
                    product_id=product['id'],
                    product_name=product['name'],
                    quantity=quantity,
                    amount=amount,
                    status='pending'
                )
                
                # Request order creation from Razorpay API
                rzp_order = payments.create_razorpay_order(session_id, amount, db_order_id)
                
                if rzp_order:
                    # Update local database order with Razorpay Order ID
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE orders 
                        SET razorpay_order_id = ? 
                        WHERE id = ?
                    ''', (rzp_order['id'], db_order_id))
                    conn.commit()
                    conn.close()
                    
                    # Prepare Razorpay options response for Checkout.js
                    razorpay_options = {
                        "key": payments.RAZORPAY_KEY_ID,
                        "amount": rzp_order['amount'],
                        "currency": rzp_order['currency'],
                        "name": "AI Agent Commerce",
                        "description": f"Purchase: {quantity}x {product['name']}",
                        "order_id": rzp_order['id'],
                        "prefill": {
                            "name": "Hackathon Buyer",
                            "email": "buyer@example.com",
                            "contact": "9999999999"
                        }
                    }
                    
                    # Clear pending session state variables
                    reset_session_state(session_id)
                    
                    return jsonify({
                        "session_id": session_id,
                        "response": "Confirming your purchase... Launching the Razorpay secure payment interface now.",
                        "state": "idle",
                        "payment_trigger": True,
                        "razorpay_options": razorpay_options
                    })
                else:
                    # Razorpay order generation failed
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE orders SET status = 'failed' WHERE id = ?", (db_order_id,))
                    conn.commit()
                    conn.close()
                    
                    reset_session_state(session_id)
                    return jsonify({
                        "session_id": session_id,
                        "response": "I encountered a payment gateway error while processing this transaction. The order has been cancelled.",
                        "state": "idle"
                    })
            except Exception as e:
                reset_session_state(session_id)
                db.log_audit(
                    session_id=session_id,
                    action_type="error",
                    reasoning=f"Critical exception occurred during order/payment creation. Error: {str(e)}",
                    payload={"error": str(e)}
                )
                return jsonify({
                    "session_id": session_id,
                    "response": "A critical system error occurred. The transaction has been aborted.",
                    "state": "idle"
                }), 500
                
        elif action == 'cancel':
            reset_session_state(session_id)
            db.log_audit(
                session_id=session_id,
                action_type="confirm_cancel",
                reasoning=f"User declined confirmation for the purchase of '{product['name']}'."
            )
            return jsonify({
                "session_id": session_id,
                "response": "Alright, I've cancelled that pending order. What else can I find for you?",
                "state": "idle"
            })
        else:
            # User typed something else. Prompt them to make a choice.
            confirm_prompt = f"Please confirm your order: {quantity}x '{product['name']}' for ₹{amount:.2f}.\nWould you like to proceed? (Type 'confirm' or 'cancel')"
            return jsonify({
                "session_id": session_id,
                "response": confirm_prompt,
                "state": "awaiting_confirmation"
            })

    # 3. State: idle (Standard path, user searches for product)
    if action == 'search':
        query = intent['query']
        max_price = intent['max_price']
        quantity = intent['quantity']
        
        matched_product, match_msg = agent.match_product(session_id, query, max_price, quantity)
        
        if matched_product:
            if match_msg != "Success":
                # Matches but out of stock or other catalog issue
                return jsonify({
                    "session_id": session_id,
                    "response": f"I found the '{matched_product['name']}', but unfortunately {match_msg.lower()}",
                    "state": "idle"
                })
            
            # Check guardrails
            guardrail = agent.check_guardrails(session_id, matched_product, quantity)
            
            if not guardrail['allowed']:
                if guardrail['escalate']:
                    state_data['state'] = 'awaiting_escalation'
                return jsonify({
                    "session_id": session_id,
                    "response": guardrail['reason'],
                    "state": state_data['state']
                })
            
            # Save order details in state for next step
            state_data['state'] = 'awaiting_confirmation'
            state_data['pending_product'] = matched_product
            state_data['pending_quantity'] = quantity
            state_data['pending_amount'] = matched_product['price'] * quantity
            state_data['requires_extra_confirm'] = guardrail['extra_confirm']
            
            return jsonify({
                "session_id": session_id,
                "response": guardrail['reason'],
                "state": "awaiting_confirmation"
            })
        else:
            return jsonify({
                "session_id": session_id,
                "response": match_msg,
                "state": "idle"
            })
            
    # Unclear actions
    return jsonify({
        "session_id": session_id,
        "response": "I didn't catch that. Try asking to buy a specific product from our catalog (e.g., 'I want to buy running shoes' or 'Get me a smart watch').",
        "state": "idle"
    })

@app.route('/api/verify-payment', methods=['POST'])
def verify_payment():
    """
    Handle Razorpay payment updates. Performs server-side signature verification
    on success payloads, or logs client-reported transaction failures.
    """
    data = request.json or {}
    session_id = data.get('session_id')
    status = data.get('status')
    
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
        
    if status == 'failed':
        razorpay_order_id = data.get('razorpay_order_id')
        error_details = data.get('error', {})
        payments.record_client_payment_failure(session_id, razorpay_order_id, error_details)
        return jsonify({"status": "recorded", "message": "Failed payment logged in audit trail."})
        
    elif status == 'success':
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_signature = data.get('razorpay_signature')
        
        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return jsonify({"error": "Missing signature verification tokens."}), 400
            
        verified = payments.verify_razorpay_payment(
            session_id=session_id,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature
        )
        
        if verified:
            return jsonify({"status": "success", "message": "Payment verified and recorded!"})
        else:
            return jsonify({"status": "failed", "message": "Payment verification failed. Invalid signature."}), 400
            
    return jsonify({"error": "Invalid verification status."}), 400

@app.route('/api/audit/<session_id>', methods=['GET'])
def audit(session_id):
    """Return the structured audit trail database entries for a session ID."""
    logs = db.get_audit_log(session_id)
    return jsonify(logs)

if __name__ == '__main__':
    # Start the web server locally
    app.run(host='127.0.0.1', port=5000, debug=True)
