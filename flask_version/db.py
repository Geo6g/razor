import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'checkout_agent.db')

def get_db_connection():
    """Establish and return a connection to the SQLite database with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database, creating orders and audit_log tables if they don't exist."""
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'paid', 'failed')),
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create audit_log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            payload TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def create_order(session_id, product_id, product_name, quantity, amount, razorpay_order_id=None, status='pending'):
    """Create a new order in the database and return the order ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (session_id, product_id, product_name, quantity, amount, razorpay_order_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, product_id, product_name, quantity, amount, razorpay_order_id, status))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Log the order creation to audit trail
    log_audit(
        session_id=session_id,
        action_type="order_created",
        reasoning=f"Database record created for order of {quantity}x '{product_name}' totaling ₹{amount:.2f}.",
        payload={
            "order_db_id": order_id,
            "product_id": product_id,
            "product_name": product_name,
            "quantity": quantity,
            "amount": amount,
            "razorpay_order_id": razorpay_order_id,
            "status": status
        }
    )
    
    return order_id

def update_order_status(razorpay_order_id, status, razorpay_payment_id=None):
    """Update status and optionally the payment ID of an order by its Razorpay order ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if razorpay_payment_id:
        cursor.execute('''
            UPDATE orders
            SET status = ?, razorpay_payment_id = ?
            WHERE razorpay_order_id = ?
        ''', (status, razorpay_payment_id, razorpay_order_id))
    else:
        cursor.execute('''
            UPDATE orders
            SET status = ?
            WHERE razorpay_order_id = ?
        ''', (status, razorpay_order_id))
    
    # Get session_id and details for audit logging
    cursor.execute('SELECT session_id, product_name, quantity, amount FROM orders WHERE razorpay_order_id = ?', (razorpay_order_id,))
    row = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    if row:
        session_id = row['session_id']
        reason = f"Order status updated to '{status}' for Razorpay order {razorpay_order_id}."
        if razorpay_payment_id:
            reason += f" Associated payment ID: {razorpay_payment_id}."
            
        log_audit(
            session_id=session_id,
            action_type=f"order_{status}",
            reasoning=reason,
            payload={
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "status": status,
                "product_name": row['product_name'],
                "quantity": row['quantity'],
                "amount": row['amount']
            }
        )
    return True

def get_order_by_razorpay_id(razorpay_order_id):
    """Retrieve an order record from the database by its Razorpay order ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE razorpay_order_id = ?', (razorpay_order_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def log_audit(session_id, action_type, reasoning, payload=None):
    """Insert an audit log record explaining the agent's actions and decisions."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Convert payload dict/list to JSON string
    payload_str = None
    if payload is not None:
        if isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)
            
    cursor.execute('''
        INSERT INTO audit_log (session_id, action_type, reasoning, payload)
        VALUES (?, ?, ?, ?)
    ''', (session_id, action_type, reasoning, payload_str))
    conn.commit()
    conn.close()

def get_audit_log(session_id):
    """Retrieve all audit logs for a given session ID, ordered chronologically."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM audit_log WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for r in rows:
        log_dict = dict(r)
        # Parse payload string back to JSON if possible
        if log_dict['payload']:
            try:
                log_dict['payload'] = json.loads(log_dict['payload'])
            except json.JSONDecodeError:
                pass
        logs.append(log_dict)
    return logs
