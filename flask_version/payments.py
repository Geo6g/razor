import os
import razorpay
from dotenv import load_dotenv
import db

# Load environment variables from .env file if present
load_dotenv()

RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')

# Lazy initialization of razorpay client to avoid crash if env vars are initially missing
_client = None

def get_razorpay_client():
    """Retrieve or initialize the Razorpay client."""
    global _client
    if _client is not None:
        return _client
        
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay environment variables RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET are missing.")
        
    _client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    return _client

def create_razorpay_order(session_id, amount_in_rupees, order_db_id):
    """
    Create a Razorpay order in test mode.
    
    Args:
        session_id (str): Current user chat session ID.
        amount_in_rupees (float): Total order cost.
        order_db_id (int): Database ID of the order.
        
    Returns:
        dict: The Razorpay order dictionary, or None if creation failed.
    """
    amount_in_paise = int(amount_in_rupees * 100)
    receipt_id = f"receipt_db_{order_db_id}"
    
    db.log_audit(
        session_id=session_id,
        action_type="payment_attempt",
        reasoning=f"Attempting to create Razorpay order for receipt '{receipt_id}' with amount ₹{amount_in_rupees:.2f} ({amount_in_paise} paise).",
        payload={
            "amount_in_paise": amount_in_paise,
            "receipt": receipt_id,
            "order_db_id": order_db_id
        }
    )
    
    try:
        client = get_razorpay_client()
        data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "payment_capture": 1 # Auto-capture payments
        }
        razorpay_order = client.order.create(data=data)
        
        db.log_audit(
            session_id=session_id,
            action_type="payment_created",
            reasoning=f"Successfully generated Razorpay order ID '{razorpay_order.get('id')}' via API.",
            payload=razorpay_order
        )
        return razorpay_order
        
    except Exception as e:
        error_msg = str(e)
        db.log_audit(
            session_id=session_id,
            action_type="payment_failure",
            reasoning=f"Failed to create Razorpay order. Error: {error_msg}",
            payload={"error": error_msg}
        )
        return None

def verify_razorpay_payment(session_id, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verify payment signature server-side.
    
    Args:
        session_id (str): Current session ID.
        razorpay_order_id (str): The Razorpay order ID.
        razorpay_payment_id (str): The payment ID returned by Checkout.
        razorpay_signature (str): The signature returned by Checkout.
        
    Returns:
        bool: True if signature is authentic, False otherwise.
    """
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    
    db.log_audit(
        session_id=session_id,
        action_type="payment_verification_attempt",
        reasoning=f"Verifying Razorpay signature server-side for order ID '{razorpay_order_id}'.",
        payload=params_dict
    )
    
    try:
        client = get_razorpay_client()
        # verify_payment_signature raises an exception if verification fails
        client.utility.verify_payment_signature(params_dict)
        
        db.log_audit(
            session_id=session_id,
            action_type="payment_success",
            reasoning=f"Razorpay payment signature successfully verified for order {razorpay_order_id}.",
            payload=params_dict
        )
        
        # Update database order status to paid
        db.update_order_status(razorpay_order_id, 'paid', razorpay_payment_id)
        return True
        
    except Exception as e:
        error_msg = str(e)
        db.log_audit(
            session_id=session_id,
            action_type="payment_failure",
            reasoning=f"Razorpay signature verification failed for order {razorpay_order_id}. Error: {error_msg}",
            payload={"error": error_msg}
        )
        
        # Mark database order status as failed
        db.update_order_status(razorpay_order_id, 'failed', razorpay_payment_id)
        return False

def record_client_payment_failure(session_id, razorpay_order_id, error_details):
    """
    Record a client-reported payment failure (e.g. card declined, user closed popup).
    
    Args:
        session_id (str): Current session ID.
        razorpay_order_id (str): Razorpay order ID.
        error_details (dict): Raw error payload from Razorpay Checkout.js.
    """
    db.log_audit(
        session_id=session_id,
        action_type="payment_failure",
        reasoning=f"Client checkout reported payment failure/decline for Razorpay order {razorpay_order_id}.",
        payload=error_details
    )
    
    # Update order in db as failed
    db.update_order_status(razorpay_order_id, 'failed')
    return True
