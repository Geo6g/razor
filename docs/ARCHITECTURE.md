# GrowthPilot AI — System Architecture & Design Specification

> **"The merchant controls the boundaries. The AI operates inside them."**

This document provides complete architectural flowcharts, sequence diagrams, and protocol specifications for the GrowthPilot AI platform.

---

## 1. High-Level System Architecture

`mermaid
flowchart TD
    subgraph Clients["Entry Channels"]
        B2C["B2C Storefront<br/>(Natural Search / Deals / Chat)"]
        M2M["External AI Buyer Agent<br/>(Machine-to-Machine CLI / Protocol)"]
        Merchant["Merchant Hub<br/>(Objectives / Boundaries / Approvals)"]
    end

    subgraph Gateway["FastAPI Application Gateway (:8000)"]
        Discovery["Discovery Manifest<br/>(/.well-known/agent.json)"]
        ChatRouter["Conversational Intent Router<br/>(/api/chat)"]
        A2ARouter["A2A Mandate Gateway<br/>(/api/agent/checkout/*)"]
        OrdersRouter["Razorpay Order Gateway<br/>(/api/create-order & /api/verify-payment)"]
    end

    subgraph CoreEngine["AI Reasoning & Margin Defense Core"]
        LLM["AI Heuristic & Intent Parser<br/>(Claude 3.5 / Deterministic Parser)"]
        ObjectiveInjector["Strategic Objective Injector<br/>(Protect Profit / Maximize Conversions / Increase AOV)"]
        
        subgraph PolicyEngine["Tripartite Policy Validation Layer"]
            Cap["Hard Discount Cap (20%)"]
            Floor["Minimum Profit Floor (Rs.400)"]
            Qty["Per-SKU Quantity Cap (5 units)"]
            Stock["Live Stock Inventory Check"]
        end
        
        subgraph RiskGate["Risk Governance & Branching Engine"]
            SafeBranch["SAFE (<= 10% Disc)<br/>Auto-Approved"]
            GateBranch["HIGH RISK (10% - 20% Disc)<br/>Waiting for Merchant Approval"]
            BlockBranch["VIOLATION (> 20% / Neg Margin)<br/>Hard Blocked (HTTP 409)"]
        end
    end

    subgraph ExternalServices["External Payment & Settlement Layer"]
        RZP_API["Razorpay API<br/>(POST /v1/orders)"]
        RZP_Modal["Razorpay Checkout.js Modal<br/>(UPI / Card / Netbanking)"]
        HMAC["HMAC-SHA256 Signature Verification<br/>(order_id + '|' + payment_id)"]
    end

    subgraph Storage["Authoritative Data Layer"]
        SQLite[("Append-Only SQLite Ledger<br/>(growthpilot.db)")]
        Triggers["Database Engine Triggers<br/>(prevent_audit_log_update / delete)"]
    end

    %% Flow Connections
    B2C --> ChatRouter
    B2C --> OrdersRouter
    M2M --> Discovery
    M2M --> A2ARouter
    Merchant --> Gateway

    ChatRouter --> LLM
    A2ARouter --> PolicyEngine
    LLM --> ObjectiveInjector --> PolicyEngine
    
    PolicyEngine --> RiskGate
    RiskGate --> SafeBranch
    RiskGate --> GateBranch
    RiskGate --> BlockBranch

    GateBranch -.->|"1-Click Manual Sign-Off & Revalidation"| Merchant
    SafeBranch --> OrdersRouter
    
    OrdersRouter --> RZP_API
    OrdersRouter --> RZP_Modal
    RZP_Modal --> HMAC
    
    Gateway --> SQLite
    Triggers -.-> SQLite
`

---

## 2. 7-Stage Live Decision Telemetry Pipeline

`mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / External Agent
    participant Hub as Merchant Settings
    participant AI as AI Reasoner
    participant Policy as Policy Validation Layer
    participant Gate as Risk Gate
    participant Exec as Action Execution
    participant Ledger as Append-Only Audit Ledger

    Customer->>AI: 1. Customer Signal ("Rs.2,499 is too expensive")
    Hub->>AI: 2. Context Evaluated (Active Objective: "Protect Profit")
    AI->>Policy: 3. Agent Proposal (Offer Free Shipping waiver / 0% discount)
    Policy->>Gate: 4. Policy Check (Margin Floor Rs.400: PASS | Discount Cap 20%: PASS)
    
    alt Safe Zone (<= 10% Discount)
        Gate->>Exec: 5. Risk: LOW -> Auto-Approved
        Exec->>Customer: 6. Action: Apply Free Shipping to Checkout
    else Approval Gate (10% - 20% Discount)
        Gate->>Exec: 5. Risk: HIGH -> WAITING FOR MERCHANT APPROVAL
        Exec->>Hub: Queued in Merchant Hub (appr_xxxx)
        Hub->>Policy: Revalidate Live Stock & Margin Floor
        Hub->>Exec: Merchant Signs Off -> Checkout Unlocked
    else Hard Boundary Violation (> 20% Discount / Qty > 5)
        Gate->>Customer: 5. Risk: BLOCKED -> Graceful Failure Explanation (HTTP 409)
    end
    
    Exec->>Ledger: 7. Commit Authoritative Event (AUD-XXXX) with SQLite Triggers
`

---

## 3. Machine-to-Machine (A2A) Commerce Protocol Flow

`mermaid
sequenceDiagram
    autonumber
    actor BuyerAgent as External Autonomous Buyer Agent
    participant Manifest as /.well-known/agent.json
    participant Catalog as /api/agent/catalog
    participant Intent as /api/agent/checkout/intent
    participant Confirm as /api/agent/checkout/confirm
    participant Razorpay as Razorpay Orders API

    BuyerAgent->>Manifest: GET /.well-known/agent.json (Discovery)
    Manifest-->>BuyerAgent: Returns manifest (policy v1.0, endpoints, supported currencies)
    
    BuyerAgent->>Catalog: GET /api/agent/catalog?category=earbuds
    Catalog-->>BuyerAgent: Returns public catalog (cost_price & internal margins stripped)
    
    BuyerAgent->>BuyerAgent: Select product & construct Purchase Mandate
    BuyerAgent->>BuyerAgent: Sign canonical JSON payload via HMAC-SHA256
    
    BuyerAgent->>Intent: POST /api/agent/checkout/intent { items, max_total, signature }
    
    alt Within Guardrails (Qty <= 5, Price Valid)
        Intent-->>BuyerAgent: HTTP 200 { intent_id: "int_xxx", status: "pending" }
        BuyerAgent->>Confirm: POST /api/agent/checkout/confirm { intent_id, buyer_id, signature }
        Confirm->>Razorpay: Create Payment Order
        Razorpay-->>Confirm: { razorpay_order_id: "order_xxx" }
        Confirm-->>BuyerAgent: HTTP 200 { status: "confirmed", razorpay_order_id }
    else Policy Breach (e.g. Qty = 12 > 5 Cap)
        Intent-->>BuyerAgent: HTTP 409 Conflict { status: "blocked", reason: "quantity_limit_exceeded", retry_suggestion: "Reduce quantity to 5 or fewer units." }
    end
`

---

## 4. Architectural Component Reference

| Layer | Technologies | Responsibilities |
| :--- | :--- | :--- |
| **Frontend** | React 18, Vite, Tailwind CSS, Lucide Icons, Recharts, Canvas Confetti | Storefront UI, Merchant Hub, Real-time Decision Inspector. |
| **Gateway & Backend** | Python 3.13, FastAPI, Uvicorn, Pydantic | API routing, heuristic parsing, objective injection, policy validation. |
| **Payments** | Razorpay Python SDK + Checkout.js | Order creation, payment capture modal, HMAC-SHA256 signature verification. |
| **Storage & Ledger** | SQLite3 with Engine Triggers | Append-only audit trail (prevent_audit_log_update/delete), catalog, orders. |
| **A2A Protocol** | HMAC-SHA256, Canonical JSON | Machine discovery manifest, cryptographic mandate verification, two-step commit. |
