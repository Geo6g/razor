import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'growthpilot.db')
CATALOG_PATH = os.path.join(os.path.dirname(__file__), 'data', 'catalog.json')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()

    # ── Core tables ──────────────────────────────────────────────────────────

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            cost_price REAL NOT NULL,
            profit_margin REAL NOT NULL,
            category TEXT NOT NULL,
            features TEXT,
            stock INTEGER NOT NULL,
            image TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'paid', 'failed')),
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            incentive_used TEXT DEFAULT 'none',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            sender TEXT NOT NULL CHECK(sender IN ('user', 'agent', 'system')),
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

    # Enforce Append-Only behavior at database engine level
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS prevent_audit_log_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Audit log is append-only and cannot be updated.');
        END;
    ''')
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Audit log is append-only and cannot be deleted.');
        END;
    ''')

    # ── NEW: Merchant settings ────────────────────────────────────────────────
    # Stores the active merchant objective and policy constraints
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS merchant_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            objective TEXT NOT NULL DEFAULT 'protect_profit',
            max_discount_pct REAL NOT NULL DEFAULT 10.0,
            min_margin REAL NOT NULL DEFAULT 400.0,
            shipping_cost REAL NOT NULL DEFAULT 100.0,
            high_risk_discount_threshold REAL NOT NULL DEFAULT 15.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Try adding column if existing db didn't have high_risk_discount_threshold
    try:
        cursor.execute('ALTER TABLE merchant_settings ADD COLUMN high_risk_discount_threshold REAL DEFAULT 15.0')
    except Exception:
        pass

    # Seed default settings row if absent
    cursor.execute('SELECT COUNT(*) FROM merchant_settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO merchant_settings (id, objective, max_discount_pct, min_margin, shipping_cost, high_risk_discount_threshold)
            VALUES (1, 'protect_profit', 10.0, 400.0, 100.0, 15.0)
        ''')

    # ── Explicit Risk Gate: Pending Approvals Table ───────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id TEXT UNIQUE NOT NULL,
            session_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            risk_level TEXT NOT NULL CHECK(risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
            status TEXT NOT NULL CHECK(status IN ('WAITING FOR MERCHANT APPROVAL', 'APPROVED', 'BLOCKED')),
            details TEXT,
            discount_pct REAL DEFAULT 0.0,
            requested_amount REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolution_reason TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approvals_status ON pending_approvals(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approvals_session ON pending_approvals(session_id)')

    # ── NEW: Strategy outcomes — closed feedback loop ─────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS strategy_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            strategy TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            customer_state TEXT,
            merchant_objective TEXT,
            result TEXT NOT NULL CHECK(result IN ('converted', 'abandoned', 'pending')),
            revenue REAL DEFAULT 0.0,
            profit_delta REAL DEFAULT 0.0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── NEW: Customer memory — lightweight per-session context ────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_memory (
            session_id TEXT PRIMARY KEY,
            products_viewed TEXT DEFAULT '[]',
            last_product_id TEXT,
            last_product_name TEXT,
            last_objection TEXT,
            incentive_offered TEXT DEFAULT 'none',
            converted INTEGER DEFAULT 0,
            abandoned_checkout INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── NEW: Checkout lifecycle events ────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkout_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            order_id INTEGER,
            razorpay_order_id TEXT,
            event_type TEXT NOT NULL CHECK(event_type IN ('created', 'opened', 'completed', 'abandoned', 'recovered')),
            product_name TEXT,
            amount REAL,
            incentive_used TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── NEW: Buyer-agent checkout intents (Step 1) ────────────────────────────
    # Each row is a signed mandate from an external AI buyer agent that
    # asks the merchant to reserve a checkout. Two-step commit:
    #   create (status=pending)  ->  confirm (status=confirmed + razorpay_order_id)
    #   -> webhook (status=paid|failed)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyer_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_id TEXT UNIQUE NOT NULL,
            buyer_id TEXT NOT NULL,
            session_id TEXT,
            mandate_signature TEXT NOT NULL,
            mandate_payload TEXT NOT NULL,
            computed_total REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            status TEXT NOT NULL CHECK(status IN ('pending', 'confirmed', 'paid', 'failed', 'expired', 'rejected')),
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            db_order_id INTEGER,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            confirmed_at TEXT,
            policy_version TEXT NOT NULL DEFAULT '1.0',
            rejection_reason TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyer_intents_buyer_id ON buyer_intents(buyer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyer_intents_status  ON buyer_intents(status)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_buyer_intents_rzp   ON buyer_intents(razorpay_order_id) WHERE razorpay_order_id IS NOT NULL')

    conn.commit()

    # Seed or sync products from catalog.json
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
                products = json.load(f)
            for p in products:
                features_val = json.dumps(p.get('features', [])) if isinstance(p.get('features'), list) else p.get('features', '[]')
                cursor.execute('''
                    INSERT OR REPLACE INTO products (id, name, description, price, cost_price, profit_margin, category, features, stock, image)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p['id'], p['name'], p['description'],
                    float(p['price']), float(p['cost_price']), float(p['profit_margin']),
                    p['category'], features_val, int(p.get('stock', 10)), p.get('image', '')
                ))
            conn.commit()
            print(f"Synced database with {len(products)} catalog products.")
        except Exception as e:
            print(f"Error seeding/syncing database: {e}")

    conn.close()

# ── Product helpers ───────────────────────────────────────────────────────────

def get_products(category=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute('SELECT * FROM products WHERE category = ?', (category,))
    else:
        cursor.execute('SELECT * FROM products')
    rows = cursor.fetchall()
    conn.close()
    products = []
    for r in rows:
        p = dict(r)
        p['features'] = json.loads(p['features']) if p['features'] else []
        products.append(p)
    return products

def get_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        p = dict(row)
        p['features'] = json.loads(p['features']) if p['features'] else []
        return p
    return None

# ── Order helpers ─────────────────────────────────────────────────────────────

def create_order(session_id, product_id, product_name, amount, razorpay_order_id=None, status='pending', incentive_used='none'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (session_id, product_id, product_name, amount, razorpay_order_id, status, incentive_used)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, product_id, product_name, amount, razorpay_order_id, status, incentive_used))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_audit(
        session_id=session_id,
        action_type="order_created",
        reasoning=f"Logged pending order {order_id} for '{product_name}' at Rs.{amount:.2f}. Incentive: '{incentive_used}'.",
        payload={"order_db_id": order_id, "product_id": product_id, "product_name": product_name,
                 "amount": amount, "razorpay_order_id": razorpay_order_id, "status": status, "incentive_used": incentive_used}
    )
    return order_id

def update_order_status(razorpay_order_id, status, razorpay_payment_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if razorpay_payment_id:
        cursor.execute('''
            UPDATE orders SET status = ?, razorpay_payment_id = ? WHERE razorpay_order_id = ?
        ''', (status, razorpay_payment_id, razorpay_order_id))
    else:
        cursor.execute('UPDATE orders SET status = ? WHERE razorpay_order_id = ?', (status, razorpay_order_id))

    cursor.execute('''
        SELECT id, session_id, product_id, product_name, amount, incentive_used
        FROM orders WHERE razorpay_order_id = ?
    ''', (razorpay_order_id,))
    row = cursor.fetchone()
    conn.commit()

    if status == 'paid' and row:
        cursor.execute('UPDATE products SET stock = MAX(0, stock - 1) WHERE id = ?', (row['product_id'],))
        conn.commit()

    conn.close()

    if row:
        session_id = row['session_id']
        reason = f"Payment outcome '{status}' for order {razorpay_order_id}."
        if razorpay_payment_id:
            reason += f" Payment ID: {razorpay_payment_id}."
        log_audit(
            session_id=session_id,
            action_type=f"payment_{status}",
            reasoning=reason,
            payload={"razorpay_order_id": razorpay_order_id, "razorpay_payment_id": razorpay_payment_id,
                     "status": status, "product_name": row['product_name'],
                     "amount": row['amount'], "incentive_used": row['incentive_used']}
        )
        # Record strategy outcome
        settings = get_merchant_settings()
        mem = get_customer_memory(session_id)
        strategy_used = _incentive_to_strategy(row['incentive_used'])
        result = 'converted' if status == 'paid' else 'abandoned'
        profit_delta = row['amount'] - (get_product(row['product_id']) or {}).get('cost_price', 0)
        record_strategy_outcome(
            session_id=session_id,
            strategy=strategy_used,
            product_id=row['product_id'],
            product_name=row['product_name'],
            customer_state=mem.get('last_objection', 'general'),
            merchant_objective=settings['objective'],
            result=result,
            revenue=row['amount'] if status == 'paid' else 0.0,
            profit_delta=profit_delta if status == 'paid' else 0.0
        )
        # Update customer memory
        if status == 'paid':
            update_customer_memory(session_id, converted=1)
            create_checkout_event(session_id, row['id'], razorpay_order_id, 'completed',
                                  row['product_name'], row['amount'], row['incentive_used'])
        else:
            update_customer_memory(session_id, abandoned_checkout=1)
            create_checkout_event(session_id, row['id'], razorpay_order_id, 'abandoned',
                                  row['product_name'], row['amount'], row['incentive_used'])
    return True

def _incentive_to_strategy(incentive):
    mapping = {
        'GROWTH10': 'offer_discount',
        'FREESHIP': 'offer_free_shipping',
        'BUNDLE': 'recommend_bundle',
        'none': 'no_incentive'
    }
    return mapping.get(incentive, 'no_incentive')

# ── Merchant settings helpers ─────────────────────────────────────────────────

def get_merchant_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM merchant_settings WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d.setdefault('high_risk_discount_threshold', 15.0)
        return d
    return {
        'objective': 'protect_profit',
        'max_discount_pct': 10.0,
        'min_margin': 400.0,
        'shipping_cost': 100.0,
        'high_risk_discount_threshold': 15.0
    }

def save_merchant_settings(objective, max_discount_pct, min_margin, shipping_cost,
                            high_risk_discount_threshold=15.0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO merchant_settings
            (id, objective, max_discount_pct, min_margin, shipping_cost, high_risk_discount_threshold, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            objective = excluded.objective,
            max_discount_pct = excluded.max_discount_pct,
            min_margin = excluded.min_margin,
            shipping_cost = excluded.shipping_cost,
            high_risk_discount_threshold = excluded.high_risk_discount_threshold,
            updated_at = excluded.updated_at
    ''', (objective, max_discount_pct, min_margin, shipping_cost, high_risk_discount_threshold))
    conn.commit()
    conn.close()


# ── Pending Approvals CRUD ────────────────────────────────────────────────────

def create_pending_approval(session_id, action_type, product_id, product_name,
                             risk_level, details, discount_pct=0.0, requested_amount=0.0):
    import uuid
    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO pending_approvals
            (approval_id, session_id, action_type, product_id, product_name,
             risk_level, status, details, discount_pct, requested_amount)
        VALUES (?, ?, ?, ?, ?, ?, 'WAITING FOR MERCHANT APPROVAL', ?, ?, ?)
    ''', (approval_id, session_id, action_type, product_id, product_name,
          risk_level, details, discount_pct, requested_amount))
    conn.commit()
    conn.close()
    return approval_id


def resolve_pending_approval(approval_id, new_status, resolution_reason=''):
    """Set status to APPROVED or BLOCKED. Returns the resolved row or None."""
    assert new_status in ('APPROVED', 'BLOCKED'), "Invalid status"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pending_approvals
        SET status = ?, resolved_at = CURRENT_TIMESTAMP, resolution_reason = ?
        WHERE approval_id = ? AND status = 'WAITING FOR MERCHANT APPROVAL'
    ''', (new_status, resolution_reason, approval_id))
    conn.commit()
    cursor.execute('SELECT * FROM pending_approvals WHERE approval_id = ?', (approval_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_approvals(status_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if status_filter:
        cursor.execute('SELECT * FROM pending_approvals WHERE status = ? ORDER BY created_at DESC LIMIT 100',
                       (status_filter,))
    else:
        cursor.execute('SELECT * FROM pending_approvals ORDER BY created_at DESC LIMIT 100')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_approval(approval_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM pending_approvals WHERE approval_id = ?', (approval_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ── Strategy outcomes & feedback loop ─────────────────────────────────────────

def record_strategy_outcome(session_id, strategy, product_id, product_name,
                             customer_state, merchant_objective, result, revenue=0.0, profit_delta=0.0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO strategy_outcomes
            (session_id, strategy, product_id, product_name, customer_state, merchant_objective, result, revenue, profit_delta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, strategy, product_id, product_name, customer_state, merchant_objective, result, revenue, profit_delta))
    conn.commit()
    conn.close()

def get_strategy_performance_stats():
    """Returns per-strategy conversion rates and revenue stats for AI context."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            strategy,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'converted' THEN 1 ELSE 0 END) as converted,
            AVG(CASE WHEN result = 'converted' THEN revenue ELSE NULL END) as avg_revenue,
            AVG(CASE WHEN result = 'converted' THEN profit_delta ELSE NULL END) as avg_profit
        FROM strategy_outcomes
        WHERE timestamp >= datetime('now', '-30 days')
        GROUP BY strategy
    ''')
    rows = cursor.fetchall()
    conn.close()
    stats = {}
    for r in rows:
        total = r['total'] or 1
        conversion_rate = round((r['converted'] / total) * 100, 1)
        stats[r['strategy']] = {
            'total': r['total'],
            'converted': r['converted'],
            'conversion_rate': conversion_rate,
            'avg_revenue': round(r['avg_revenue'] or 0, 2),
            'avg_profit': round(r['avg_profit'] or 0, 2)
        }
    return stats

# ── Customer memory helpers ───────────────────────────────────────────────────

def get_customer_memory(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM customer_memory WHERE session_id = ?', (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d['products_viewed'] = json.loads(d['products_viewed'])
        except Exception:
            d['products_viewed'] = []
        return d
    return {
        'session_id': session_id,
        'products_viewed': [],
        'last_product_id': None,
        'last_product_name': None,
        'last_objection': None,
        'incentive_offered': 'none',
        'converted': 0,
        'abandoned_checkout': 0
    }

def update_customer_memory(session_id, **kwargs):
    mem = get_customer_memory(session_id)
    # Merge kwargs
    if 'products_viewed' in kwargs and isinstance(kwargs['products_viewed'], list):
        existing = mem.get('products_viewed', [])
        for pid in kwargs['products_viewed']:
            if pid not in existing:
                existing.append(pid)
        kwargs['products_viewed'] = json.dumps(existing)
    elif 'products_viewed' in kwargs:
        kwargs['products_viewed'] = json.dumps(kwargs['products_viewed'])
    else:
        kwargs['products_viewed'] = json.dumps(mem.get('products_viewed', []))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO customer_memory
            (session_id, products_viewed, last_product_id, last_product_name,
             last_objection, incentive_offered, converted, abandoned_checkout, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET
            products_viewed      = excluded.products_viewed,
            last_product_id      = COALESCE(excluded.last_product_id, last_product_id),
            last_product_name    = COALESCE(excluded.last_product_name, last_product_name),
            last_objection       = COALESCE(excluded.last_objection, last_objection),
            incentive_offered    = COALESCE(excluded.incentive_offered, incentive_offered),
            converted            = CASE WHEN excluded.converted = 1 THEN 1 ELSE converted END,
            abandoned_checkout   = CASE WHEN excluded.abandoned_checkout = 1 THEN 1 ELSE abandoned_checkout END,
            last_updated         = CURRENT_TIMESTAMP
    ''', (
        session_id,
        kwargs.get('products_viewed', json.dumps(mem.get('products_viewed', []))),
        kwargs.get('last_product_id', mem.get('last_product_id')),
        kwargs.get('last_product_name', mem.get('last_product_name')),
        kwargs.get('last_objection', mem.get('last_objection')),
        kwargs.get('incentive_offered', mem.get('incentive_offered', 'none')),
        kwargs.get('converted', mem.get('converted', 0)),
        kwargs.get('abandoned_checkout', mem.get('abandoned_checkout', 0))
    ))
    conn.commit()
    conn.close()

# ── Checkout event lifecycle ──────────────────────────────────────────────────

def create_checkout_event(session_id, order_id, razorpay_order_id, event_type,
                           product_name=None, amount=None, incentive_used=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO checkout_events
            (session_id, order_id, razorpay_order_id, event_type, product_name, amount, incentive_used)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, order_id, razorpay_order_id, event_type, product_name, amount, incentive_used))
    conn.commit()
    conn.close()

def get_abandoned_checkouts(session_id=None):
    """Return checkout_events of type 'created' with no corresponding 'completed' for same session+order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute('''
            SELECT ce.* FROM checkout_events ce
            WHERE ce.event_type = 'abandoned' AND ce.session_id = ?
            AND NOT EXISTS (
                SELECT 1 FROM checkout_events ce2
                WHERE ce2.session_id = ce.session_id
                AND ce2.order_id = ce.order_id
                AND ce2.event_type = 'recovered'
            )
            ORDER BY ce.timestamp DESC LIMIT 1
        ''', (session_id,))
    else:
        cursor.execute('''
            SELECT ce.* FROM checkout_events ce
            WHERE ce.event_type = 'abandoned'
            AND NOT EXISTS (
                SELECT 1 FROM checkout_events ce2
                WHERE ce2.session_id = ce.session_id
                AND ce2.order_id = ce.order_id
                AND ce2.event_type = 'recovered'
            )
            ORDER BY ce.timestamp DESC LIMIT 20
        ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def simulate_abandonment(session_id):
    """Demo helper: mark the most recent pending checkout as abandoned."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Find most recent pending order for this session
    cursor.execute('''
        SELECT id, product_id, product_name, amount, razorpay_order_id, incentive_used
        FROM orders
        WHERE session_id = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    ''', (session_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    cursor.execute("UPDATE orders SET status = 'failed' WHERE id = ?", (row['id'],))
    conn.commit()
    conn.close()

    create_checkout_event(
        session_id, row['id'], row['razorpay_order_id'], 'abandoned',
        row['product_name'], row['amount'], row['incentive_used']
    )
    update_customer_memory(session_id, abandoned_checkout=1)
    log_audit(session_id, 'checkout_abandoned',
              f"Demo abandonment triggered for order {row['id']} ('{row['product_name']}').",
              {'order_id': row['id'], 'product_name': row['product_name'], 'amount': row['amount']})
    return dict(row)

# ── Buyer-agent intent helpers (Step 1) ───────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_buyer_intent(intent_id, buyer_id, session_id, mandate_signature,
                        mandate_payload, computed_total, currency,
                        status, created_at, expires_at, policy_version="1.0"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO buyer_intents
            (intent_id, buyer_id, session_id, mandate_signature, mandate_payload,
             computed_total, currency, status, created_at, expires_at, policy_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (intent_id, buyer_id, session_id, mandate_signature,
          json.dumps(mandate_payload), computed_total, currency, status,
          created_at, expires_at, policy_version))
    conn.commit()
    conn.close()
    log_audit(
        session_id=session_id or f"buyer:{buyer_id}",
        action_type="buyer_intent_created",
        reasoning=(f"Buyer agent '{buyer_id}' created checkout intent {intent_id} "
                   f"for Rs.{computed_total:.2f} {currency} (policy v{policy_version})."),
        payload={
            "intent_id": intent_id, "buyer_id": buyer_id,
            "computed_total": computed_total, "currency": currency,
            "expires_at": expires_at, "items": mandate_payload.get("items", []),
        }
    )
    return intent_id


def get_buyer_intent(intent_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM buyer_intents WHERE intent_id = ?', (intent_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("mandate_payload"):
        try:
            d["mandate_payload"] = json.loads(d["mandate_payload"])
        except Exception:
            pass
    return d


def get_buyer_intent_by_razorpay_order(razorpay_order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM buyer_intents WHERE razorpay_order_id = ?', (razorpay_order_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("mandate_payload"):
        try:
            d["mandate_payload"] = json.loads(d["mandate_payload"])
        except Exception:
            pass
    return d


def update_buyer_intent_status(intent_id, status, **fields):
    """
    Update buyer_intents.status (and any of: razorpay_order_id, razorpay_payment_id,
    db_order_id, confirmed_at, rejection_reason).
    Emits a buyer_intent_<status> audit row.
    """
    allowed_status = {"pending", "confirmed", "paid", "failed", "expired", "rejected"}
    if status not in allowed_status:
        raise ValueError(f"invalid status: {status}")

    setters = ["status = ?"]
    values: list = [status]
    for k in ("razorpay_order_id", "razorpay_payment_id", "db_order_id",
              "confirmed_at", "rejection_reason"):
        if k in fields and fields[k] is not None:
            setters.append(f"{k} = ?")
            values.append(fields[k])

    values.append(intent_id)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE buyer_intents SET {', '.join(setters)} WHERE intent_id = ?", values)
    conn.commit()

    # Pull the row for the audit payload
    cursor.execute('SELECT * FROM buyer_intents WHERE intent_id = ?', (intent_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        log_audit(
            session_id=d.get("session_id") or f"buyer:{d.get('buyer_id')}",
            action_type=f"buyer_intent_{status}",
            reasoning=(f"Buyer intent {intent_id} -> status '{status}'."),
            payload={
                "intent_id": intent_id,
                "buyer_id": d.get("buyer_id"),
                "computed_total": d.get("computed_total"),
                "currency": d.get("currency"),
                "razorpay_order_id": d.get("razorpay_order_id"),
                "razorpay_payment_id": d.get("razorpay_payment_id"),
                "db_order_id": d.get("db_order_id"),
                "rejection_reason": d.get("rejection_reason"),
                "policy_version": d.get("policy_version"),
                **{k: v for k, v in fields.items() if k in ("razorpay_order_id", "razorpay_payment_id", "db_order_id", "confirmed_at", "rejection_reason")},
            }
        )
    return True


# ── Conversations helpers ─────────────────────────────────────────────────────

def add_chat_message(session_id, sender, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversations (session_id, sender, message) VALUES (?, ?, ?)',
                   (session_id, sender, message))
    conn.commit()
    conn.close()

def get_chat_history(session_id, limit=10):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sender, message, timestamp FROM conversations
        WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?
    ''', (session_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))

def get_all_chat_history(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT sender, message, timestamp FROM conversations WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Audit logging ─────────────────────────────────────────────────────────────

def log_audit(session_id, action_type, reasoning, payload=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    payload_str = json.dumps(payload) if payload else None
    cursor.execute('INSERT INTO audit_log (session_id, action_type, reasoning, payload) VALUES (?, ?, ?, ?)',
                   (session_id, action_type, reasoning, payload_str))
    log_id = cursor.lastrowid or 1
    conn.commit()
    conn.close()
    return f"AUD-{log_id:04d}"

def get_audit_log(session_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute('SELECT * FROM audit_log WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
    else:
        cursor.execute('SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 50')
    rows = cursor.fetchall()
    conn.close()
    logs = []
    for r in rows:
        d = dict(r)
        if d['payload']:
            try:
                d['payload'] = json.loads(d['payload'])
            except Exception:
                pass
        logs.append(d)
    return logs

# ── Merchant dashboard metrics ────────────────────────────────────────────────

def get_merchant_metrics():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(DISTINCT session_id) FROM conversations')
    total_convs = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'paid'")
    completed_sales = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('failed', 'pending')")
    failed_orders = cursor.fetchone()[0] or 0

    conversion_rate = round((completed_sales / total_convs * 100), 1) if total_convs > 0 else 0.0

    cursor.execute("SELECT SUM(amount) FROM orders WHERE status = 'paid'")
    revenue = cursor.fetchone()[0] or 0.0

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'paid' AND incentive_used != 'none'")
    incentives_used = cursor.fetchone()[0] or 0

    # Profit preserved = sum of (amount - cost_price) for paid orders
    cursor.execute('''
        SELECT SUM(o.amount - p.cost_price)
        FROM orders o JOIN products p ON o.product_id = p.id
        WHERE o.status = 'paid'
    ''')
    profit_preserved = cursor.fetchone()[0] or 0.0

    # Abandonment rate
    cursor.execute("SELECT COUNT(*) FROM checkout_events WHERE event_type = 'abandoned'")
    total_abandoned = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM checkout_events WHERE event_type IN ('abandoned','completed')")
    total_checkouts = cursor.fetchone()[0] or 0
    abandonment_rate = round((total_abandoned / total_checkouts * 100), 1) if total_checkouts > 0 else 0.0

    # Recovery rate
    cursor.execute("SELECT COUNT(*) FROM checkout_events WHERE event_type = 'recovered'")
    recovered = cursor.fetchone()[0] or 0
    recovery_rate = round((recovered / total_abandoned * 100), 1) if total_abandoned > 0 else 0.0

    # AI proposal approval rate (validated vs rejected)
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE action_type = 'proposal_approved'")
    approved = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE action_type = 'proposal_rejected'")
    rejected = cursor.fetchone()[0] or 0
    total_proposals = approved + rejected
    approval_rate = round((approved / total_proposals * 100), 1) if total_proposals > 0 else 100.0

    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE action_type LIKE 'agent_decision_%'")
    decisions_made = cursor.fetchone()[0] or 0

    conn.close()
    return {
        "total_conversations": total_convs,
        "conversion_rate": conversion_rate,
        "revenue_influenced": round(revenue, 2),
        "completed_sales": completed_sales,
        "abandoned_conversations": total_abandoned,
        "incentives_used": incentives_used,
        "profit_preserved": round(profit_preserved, 2),
        "abandonment_rate": abandonment_rate,
        "recovery_rate": recovery_rate,
        "approval_rate": approval_rate,
        "decisions_made": decisions_made
    }

def get_dashboard_chart_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Revenue by day
    cursor.execute('''
        SELECT DATE(created_at) as date, SUM(amount) as revenue, COUNT(*) as sales
        FROM orders WHERE status = 'paid'
        GROUP BY DATE(created_at) ORDER BY date ASC LIMIT 7
    ''')
    revenue_rows = cursor.fetchall()
    revenue_chart = [{"date": r['date'], "revenue": round(r['revenue'], 2), "sales": r['sales']} for r in revenue_rows]
    if not revenue_chart:
        revenue_chart = [{"date": datetime.today().strftime('%Y-%m-%d'), "revenue": 0.0, "sales": 0}]

    # Strategy performance for chart
    cursor.execute('''
        SELECT action_type, COUNT(*) as count
        FROM audit_log
        WHERE action_type IN ('offered_discount','offered_free_shipping','recommended_cheaper_alternative',
                              'checkout_proceed','recommended_bundle','compare_products','ask_clarifying_question')
        GROUP BY action_type
    ''')
    decision_rows = cursor.fetchall()
    label_map = {
        "offered_discount": "Discount",
        "offered_free_shipping": "Free Shipping",
        "recommended_cheaper_alternative": "Alt. Product",
        "checkout_proceed": "Direct Buy",
        "recommended_bundle": "Bundle",
        "compare_products": "Comparison",
        "ask_clarifying_question": "Clarify"
    }
    decisions_chart = [{"name": label_map.get(r['action_type'], r['action_type']), "value": r['count']} for r in decision_rows]
    if not decisions_chart:
        decisions_chart = [{"name": "No data yet", "value": 1}]

    # Product performance
    cursor.execute('''
        SELECT product_name, COUNT(*) as sales_count, SUM(amount) as total_sales
        FROM orders WHERE status = 'paid'
        GROUP BY product_name ORDER BY sales_count DESC LIMIT 5
    ''')
    products_chart = [{"name": r['product_name'], "sales": r['sales_count'], "revenue": round(r['total_sales'], 2)}
                      for r in cursor.fetchall()]

    # Strategy performance detail for feedback loop panel
    stats = get_strategy_performance_stats()
    strategy_performance_chart = [
        {"strategy": k, "conversion_rate": v['conversion_rate'],
         "total": v['total'], "converted": v['converted'], "avg_revenue": v['avg_revenue']}
        for k, v in stats.items()
    ]

    conn.close()
    return {
        "revenue_chart": revenue_chart,
        "decisions_chart": decisions_chart,
        "products_chart": products_chart,
        "strategy_performance": strategy_performance_chart
    }


def reset_demo_data():
    """Resets demo orders, conversations, approvals, and metrics to a fresh state for a clean demo recording."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DROP TRIGGER IF EXISTS prevent_audit_log_update")
    cursor.execute("DROP TRIGGER IF EXISTS prevent_audit_log_delete")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM conversations")
    cursor.execute("DELETE FROM checkout_events")
    cursor.execute("DELETE FROM customer_memory")
    cursor.execute("DELETE FROM pending_approvals")
    cursor.execute("DELETE FROM strategy_outcomes")
    cursor.execute("DELETE FROM buyer_intents")
    cursor.execute("DELETE FROM audit_log")

    # Recreate immutable audit triggers
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS prevent_audit_log_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(FAIL, 'Audit log entries are immutable and cannot be modified.');
        END;
    ''')
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(FAIL, 'Audit log entries are immutable and cannot be deleted.');
        END;
    ''')

    conn.commit()
    conn.close()

    # Reset merchant settings to default Protect Profit state
    save_merchant_settings(
        objective='protect_profit',
        max_discount_pct=20.0,
        min_margin=400.0,
        shipping_cost=100.0,
        high_risk_discount_threshold=10.0
    )

    # Re-sync products and initial log
    init_db()
    log_audit("system", "system_initialized", "GrowthPilot demo database cleanly reset to initial state.")
    return {"status": "success", "message": "Demo data and metrics successfully reset to fresh state."}
