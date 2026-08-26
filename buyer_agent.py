"""
GrowthPilot AI - Reference Buyer Agent

Agent Commerce Gateway designed around emerging agent-commerce patterns.
A standalone script that exercises the full /api/agent/* flow against
the local merchant. Two modes:

  python buyer_agent.py            # happy path (Autonomous purchase flow)
  python buyer_agent.py --block    # policy-block path (12 earbuds - Graceful Failure)

Demonstrates bounded money actions, cryptographic mandate signing, and graceful failure handling.
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("This script needs the 'requests' library. Install with: pip install requests")
    sys.exit(1)

# Load .env so AGENT_BUYER_SECRET and RAZORPAY_KEY_SECRET work without flags
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# -- Signing (must match backend/agent_buyer.py) -----------------------------

def _normalize_obj(obj):
    if isinstance(obj, dict):
        return {k: _normalize_obj(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_normalize_obj(v) for v in obj]
    elif isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def canonical_json(obj):
    norm = _normalize_obj(obj)
    return json.dumps(norm, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_mandate(payload, secret):
    msg = canonical_json(payload).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def resolve_secret(args):
    s = args.secret or os.getenv("AGENT_BUYER_SECRET") or os.getenv("RAZORPAY_KEY_SECRET")
    if not s:
        print("[ERROR] No signing secret found. Set AGENT_BUYER_SECRET in .env or pass --secret <secret>")
        sys.exit(1)
    return s


# -- Steps -------------------------------------------------------------------

def step_manifest(base):
    r = requests.get(f"{base}/.well-known/agent.json", timeout=10)
    r.raise_for_status()
    m = r.json()
    print(f"[1] manifest  -> {m['name']} (policy v{m['policy_version']})")
    print(f"    checkout_intent endpoint: {m['endpoints']['checkout_intent']}")
    return m


def step_catalog(base, category="earbuds"):
    r = requests.get(f"{base}/api/agent/catalog", params={"category": category}, timeout=10)
    r.raise_for_status()
    c = r.json()
    print(f"[2] catalog   -> {c['count']} {category} products (currency={c['currency']})")
    if not c["products"]:
        print("    no products returned")
        sys.exit(1)
    return c


def build_mandate(product_id, quantity, max_unit_price, secret,
                  buyer_id, session_id, max_total, ttl_seconds=900):
    items = [{"product_id": product_id, "quantity": quantity, "max_unit_price": max_unit_price}]
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "buyer_id":   buyer_id,
        "session_id": session_id,
        "currency":   "INR",
        "max_total":  max_total,
        "expires_at": expires_at,
        "items":      items,
    }
    signature = sign_mandate(payload, secret)
    payload["signature"] = signature
    return payload


def step_intent(base, mandate):
    r = requests.post(f"{base}/api/agent/checkout/intent", json=mandate, timeout=10)
    return r


def step_confirm(base, intent_id, buyer_id, mandate, secret):
    confirm = {
        "intent_id": intent_id,
        "buyer_id":  buyer_id,
        "signature": mandate["signature"],
    }
    r = requests.post(f"{base}/api/agent/checkout/confirm", json=confirm, timeout=10)
    return r


def step_status(base, intent_id):
    r = requests.get(f"{base}/api/agent/orders/{intent_id}", timeout=10)
    return r


# -- Modes -------------------------------------------------------------------

def run_happy(base, secret):
    print("=================================================================")
    print(" [AI BUYER SIMULATION] Happy Path Autonomous Buyer Transaction")
    print("=================================================================")
    manifest = step_manifest(base)
    catalog  = step_catalog(base, "earbuds")
    product  = catalog["products"][0]
    print(f"    picked: {product['id']} '{product['name']}' @ Rs.{product['price']:,}")

    buyer_id   = f"buyer_demo_{uuid.uuid4().hex[:6]}"
    session_id = f"session_{uuid.uuid4().hex[:6]}"
    mandate = build_mandate(
        product_id=product["id"],
        quantity=1,
        max_unit_price=product["price"],
        secret=secret,
        buyer_id=buyer_id,
        session_id=session_id,
        max_total=product["price"],
    )

    print(f"[3] intent    -> POST /api/agent/checkout/intent (qty=1, max_total={product['price']})")
    r = step_intent(base, mandate)
    print(f"    HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text); sys.exit(1)
    intent = r.json()
    print(f"    intent_id={intent['intent_id']}  computed_total={intent['computed_total']}  status={intent['status']}")

    print(f"[4] confirm   -> POST /api/agent/checkout/confirm (Two-Step Commit)")
    r = step_confirm(base, intent["intent_id"], buyer_id, mandate, secret)
    print(f"    HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text); sys.exit(1)
    conf = r.json()
    print(f"    razorpay_order_id={conf.get('razorpay_order_id')}  status={conf['status']}")

    print(f"[5] status    -> GET /api/agent/orders/{intent['intent_id']}")
    r = step_status(base, intent["intent_id"])
    print(f"    HTTP {r.status_code}  status={r.json()['status']}")

    print("\n[OK] Happy Path Completed Successfully!")
    print(f"     Payment Order: Razorpay Order ID '{conf.get('razorpay_order_id')}' created & authorized by merchant backend.")
    print("     Audit Trail: Recorded in Append-Only Audit Ledger (see Merchant Hub -> Activity Ledger).")
    return 0


def run_block(base, secret):
    print("=================================================================")
    print(" [AI BUYER SIMULATION] Policy Block Violation (Graceful Failure)")
    print("=================================================================")
    manifest = step_manifest(base)
    catalog  = step_catalog(base, "earbuds")
    product  = catalog["products"][0]
    print(f"    picked: {product['id']} '{product['name']}'")

    buyer_id   = f"buyer_demo_{uuid.uuid4().hex[:6]}"
    session_id = f"session_{uuid.uuid4().hex[:6]}"
    # 12 earbuds - over the per-SKU cap of 5
    mandate = build_mandate(
        product_id=product["id"],
        quantity=12,
        max_unit_price=product["price"] * 12,
        secret=secret,
        buyer_id=buyer_id,
        session_id=session_id,
        max_total=product["price"] * 12,
    )

    print(f"[3] intent    -> POST /api/agent/checkout/intent (qty=12 - violates max cap of 5)")
    r = step_intent(base, mandate)
    print(f"    HTTP {r.status_code}")
    body = r.json()
    if r.status_code == 409 and body.get("error") == "policy_block":
        print(f"    reason            : {body['reason']}")
        print(f"    retry_suggestion  : {body['retry_suggestion']}")
        print(f"    max_allowed_per_sku: {body['max_allowed_per_sku']}")
        print("\n[OK] Policy Block: Graceful Failure Handled Successfully!")
        print("     Server returned HTTP 409 with explainable retry_suggestion.")
        print("     Audit Trail: See Merchant Hub -> Activity Ledger for buyer_intent_rejected entry.")
        return 0
    else:
        print(f"    unexpected response: {r.status_code} {r.text}")
        return 1


# -- Entry point -------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Reference buyer agent for GrowthPilot AI.")
    p.add_argument("--base-url", default=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--secret",   default=None, help="HMAC secret (falls back to AGENT_BUYER_SECRET / RAZORPAY_KEY_SECRET)")
    p.add_argument("--block",    action="store_true", help="Run the policy-block demo path (12 earbuds).")
    args = p.parse_args()

    secret = resolve_secret(args)
    base   = args.base_url.rstrip("/")
    print(f"-> buyer agent target: {base}")
    print(f"-> signing with secret: {secret[:4]}*** (len {len(secret)})")
    print()
    if args.block:
        return run_block(base, secret)
    return run_happy(base, secret)


if __name__ == "__main__":
    sys.exit(main())


