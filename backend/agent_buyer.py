"""
GrowthPilot AI — Buyer-Agent Surface (Step 1)

This module is the seller-side counterpart to backend/agent.py.
It exposes the surfaces that an external AI buyer agent would call
to transact with this merchant end to end:

  GET  /.well-known/agent.json
  GET  /api/agent/catalog
  GET  /api/agent/policy
  POST /api/agent/checkout/intent
  POST /api/agent/checkout/confirm
  GET  /api/agent/orders/{intent_id}
  POST /api/agent/webhook/payment

Signing model: every checkout intent is signed with HMAC-SHA256 over a
canonical (sorted-keys) JSON of the mandate payload, using a shared
secret. We fall back to RAZORPAY_KEY_SECRET if AGENT_BUYER_SECRET is not
set, so a fresh checkout with no .env never breaks the demo.

evaluate_intent_policy() is the minimal policy evaluator for Step 1.
Step 2 will replace it with the full policy.py module; the endpoints
keep the same call shape.
"""

import os
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

AGENT_BUYER_SECRET = os.getenv("AGENT_BUYER_SECRET") or os.getenv("RAZORPAY_KEY_SECRET") or ""
POLICY_VERSION = "1.0"
MIN_INTENT_VERSION = "1.0"

# Per-SKU guardrail cap (matches the seller-side check_guardrails cap of 5)
MAX_QTY_PER_SKU = 5

# Currencies we accept
ACCEPTED_CURRENCIES = {"INR"}


# ── Manifest ──────────────────────────────────────────────────────────────────

AGENT_MANIFEST: Dict[str, Any] = {
    "name": "GrowthPilot AI Merchant",
    "description": "Agent Commerce Gateway designed around emerging agent-commerce patterns.",
    "version": POLICY_VERSION,
    "policy_version": POLICY_VERSION,
    "currencies": sorted(ACCEPTED_CURRENCIES),
    "endpoints": {
        "manifest":        "/.well-known/agent.json",
        "catalog":         "/api/agent/catalog",
        "policy":          "/api/agent/policy",
        "checkout_intent": "/api/agent/checkout/intent",
        "checkout_confirm":"/api/agent/checkout/confirm",
        "order_status":    "/api/agent/orders/{intent_id}",
        "webhook":         "/api/agent/webhook/payment",
    },
    "actions": [
        "discover_catalog",
        "preview_policy",
        "create_checkout_intent",
        "confirm_checkout",
        "poll_order_status",
    ],
    "limits": {
        "max_quantity_per_sku": MAX_QTY_PER_SKU,
        "max_intent_ttl_seconds": 900,
    },
    "gateway_type": "Agent Commerce Gateway designed around emerging agent-commerce patterns.",
    "auth": {
        "scheme": "hmac-sha256",
        "header": "X-Agent-Signature",
        "canonicalization": "sorted-keys-utf8-json",
    },
}

# Per-category / per-SKU guardrails exposed to buyer agents.
# Kept separate from merchant_settings so the merchant can change tactics
# (max_discount_pct, shipping_cost) without invalidating buyer-agent caches.
AGENT_BUYER_POLICY: Dict[str, Any] = {
    "version": POLICY_VERSION,
    "max_quantity_per_sku": MAX_QTY_PER_SKU,
    "max_intent_ttl_seconds": 900,
    "currencies": sorted(ACCEPTED_CURRENCIES),
    "blocked_categories": [],
    "max_lines_per_intent": 10,
    "max_total_per_intent_inr": 200000.0,
}


# ── Canonical JSON & signing ──────────────────────────────────────────────────

def _normalize_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize_obj(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_normalize_obj(v) for v in obj]
    elif isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, whole-number normalized, no whitespace, UTF-8."""
    norm = _normalize_obj(obj)
    return json.dumps(norm, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_mandate(payload: Dict[str, Any], secret: Optional[str] = None) -> str:
    """Return hex HMAC-SHA256 over canonical_json(payload)."""
    secret_bytes = (secret or AGENT_BUYER_SECRET).encode("utf-8")
    msg = canonical_json(payload).encode("utf-8")
    return hmac.new(secret_bytes, msg, hashlib.sha256).hexdigest()


def verify_mandate(payload: Dict[str, Any], signature: str, secret: Optional[str] = None) -> bool:
    if not signature:
        return False
    expected = sign_mandate(payload, secret)
    try:
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


# ── Policy evaluation (seed for Step 2) ───────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Accept "Z" suffix
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def evaluate_intent_policy(
    intent: Dict[str, Any],
    products_by_id: Dict[str, Dict[str, Any]],
    merchant_settings: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Minimal Step-1 policy check on a checkout intent.

    Enforces:
      - currency allowed
      - intent not expired
      - every line item: known SKU, in stock, qty <= MAX_QTY_PER_SKU,
        unit price within merchant + buyer's max_unit_price
      - computed total within buyer's max_total
      - line count within cap

    Returns:
      {
        "allowed": bool,
        "reason": str,
        "retry_suggestion": str,
        "computed_total": float,
        "line_items": [{"product_id", "name", "quantity", "unit_price", "line_total"}],
        "max_allowed_per_sku": int,
      }
    """
    currency = intent.get("currency")
    if currency not in ACCEPTED_CURRENCIES:
        return {
            "allowed": False,
            "reason": f"currency '{currency}' not accepted",
            "retry_suggestion": f"use one of: {sorted(ACCEPTED_CURRENCIES)}",
            "computed_total": 0.0,
            "line_items": [],
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }

    expires_at = _parse_iso(intent.get("expires_at", ""))
    if not expires_at:
        return {
            "allowed": False,
            "reason": "missing or invalid expires_at",
            "retry_suggestion": "send ISO-8601 UTC timestamp with Z suffix",
            "computed_total": 0.0,
            "line_items": [],
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }
    if expires_at <= _now_utc():
        return {
            "allowed": False,
            "reason": "intent expired",
            "retry_suggestion": "issue a new intent with a future expires_at",
            "computed_total": 0.0,
            "line_items": [],
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }

    items = intent.get("items") or []
    if not items:
        return {
            "allowed": False,
            "reason": "no line items",
            "retry_suggestion": "include at least one item",
            "computed_total": 0.0,
            "line_items": [],
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }

    if len(items) > AGENT_BUYER_POLICY["max_lines_per_intent"]:
        return {
            "allowed": False,
            "reason": f"too many line items ({len(items)} > {AGENT_BUYER_POLICY['max_lines_per_intent']})",
            "retry_suggestion": f"split into multiple intents (max {AGENT_BUYER_POLICY['max_lines_per_intent']} lines each)",
            "computed_total": 0.0,
            "line_items": [],
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }

    line_items: List[Dict[str, Any]] = []
    computed_total = 0.0
    for it in items:
        pid = it.get("product_id")
        qty = int(it.get("quantity") or 0)
        max_unit = it.get("max_unit_price")

        if qty <= 0:
            return {
                "allowed": False,
                "reason": f"non-positive quantity for {pid}",
                "retry_suggestion": "send quantity >= 1",
                "computed_total": 0.0,
                "line_items": [],
                "max_allowed_per_sku": MAX_QTY_PER_SKU,
            }
        if qty > MAX_QTY_PER_SKU:
            return {
                "allowed": False,
                "status": "blocked",
                "reason": "quantity_limit_exceeded",
                "retry_suggestion": f"Reduce quantity to {MAX_QTY_PER_SKU} or fewer units.",
                "computed_total": 0.0,
                "line_items": [],
                "max_allowed_per_sku": MAX_QTY_PER_SKU,
            }

        product = products_by_id.get(pid)
        if not product:
            return {
                "allowed": False,
                "reason": f"unknown product_id '{pid}'",
                "retry_suggestion": "fetch /api/agent/catalog for the current SKU list",
                "computed_total": 0.0,
                "line_items": [],
                "max_allowed_per_sku": MAX_QTY_PER_SKU,
            }
        if product.get("stock", 0) < qty:
            return {
                "allowed": False,
                "reason": f"insufficient stock for {pid} (requested {qty}, available {product.get('stock', 0)})",
                "retry_suggestion": f"reduce quantity to {product.get('stock', 0)} or pick another SKU",
                "computed_total": 0.0,
                "line_items": [],
                "max_allowed_per_sku": MAX_QTY_PER_SKU,
            }

        unit_price = float(product["price"])
        if max_unit is not None and unit_price > float(max_unit):
            return {
                "allowed": False,
                "reason": f"unit price {unit_price} exceeds buyer max_unit_price {max_unit} for {pid}",
                "retry_suggestion": f"raise max_unit_price to at least {unit_price} or pick a cheaper SKU",
                "computed_total": 0.0,
                "line_items": [],
                "max_allowed_per_sku": MAX_QTY_PER_SKU,
            }

        line_total = unit_price * qty
        computed_total += line_total
        line_items.append({
            "product_id": pid,
            "name": product["name"],
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": round(line_total, 2),
        })

    max_total = float(intent.get("max_total") or 0)
    if max_total < computed_total:
        return {
            "allowed": False,
            "reason": f"computed total {computed_total:.2f} exceeds buyer max_total {max_total:.2f}",
            "retry_suggestion": f"raise max_total to at least {computed_total:.2f} or drop line items",
            "computed_total": round(computed_total, 2),
            "line_items": line_items,
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }

    if computed_total > AGENT_BUYER_POLICY["max_total_per_intent_inr"]:
        return {
            "allowed": False,
            "reason": f"computed total {computed_total:.2f} exceeds merchant per-intent cap {AGENT_BUYER_POLICY['max_total_per_intent_inr']:.2f}",
            "retry_suggestion": f"split into multiple intents under {AGENT_BUYER_POLICY['max_total_per_intent_inr']:.2f}",
            "computed_total": round(computed_total, 2),
            "line_items": line_items,
            "max_allowed_per_sku": MAX_QTY_PER_SKU,
        }

    return {
        "allowed": True,
        "reason": "intent within all policy bounds",
        "retry_suggestion": "",
        "computed_total": round(computed_total, 2),
        "line_items": line_items,
        "max_allowed_per_sku": MAX_QTY_PER_SKU,
    }


# ── Intent-id helper ──────────────────────────────────────────────────────────

def new_intent_id() -> str:
    return f"int_{uuid.uuid4().hex[:12]}"


# ── Public catalog projection ─────────────────────────────────────────────────
# Strips cost_price and profit_margin — a buyer agent should not learn
# the merchant's economics.

def project_product_for_buyer(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id":          p["id"],
        "name":        p["name"],
        "description": p.get("description", ""),
        "price":       p["price"],
        "category":    p.get("category", ""),
        "features":    p.get("features", []) or [],
        "stock":       p.get("stock", 0),
        "image":       p.get("image", ""),
    }


def build_intent_template() -> Dict[str, Any]:
    """A self-documenting example mandate for the catalog response."""
    return {
        "buyer_id":   "buyer_<your-agent-id>",
        "session_id": "session_<optional>",
        "currency":   "INR",
        "max_total":  0,
        "expires_at": "2026-12-31T23:59:59Z",
        "items": [
            {"product_id": "prod_xxx", "quantity": 1, "max_unit_price": 0}
        ],
        "signature": "<hmac-sha256 of the payload without this field>",
    }
