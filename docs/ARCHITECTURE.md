# GrowthPilot AI — System Architecture & Design Specification

> **"The merchant controls the boundaries. The AI operates inside them."**

This document provides complete architectural flowcharts, sequence diagrams, and protocol specifications for the GrowthPilot AI platform.

---

## 1. High-Level System Architecture

```mermaid
graph TD
    classDef client fill:#1E293B,stroke:#F7931A,stroke-width:2px,color:#FFFFFF;
    classDef gateway fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#FFFFFF;
    classDef core fill:#111827,stroke:#A855F7,stroke-width:2px,color:#FFFFFF;
    classDef policy fill:#022C22,stroke:#10B981,stroke-width:2px,color:#FFFFFF;
    classDef payment fill:#451A03,stroke:#F59E0B,stroke-width:2px,color:#FFFFFF;
    classDef storage fill:#1F2937,stroke:#64748B,stroke-width:2px,color:#FFFFFF;

    subgraph ChannelLayer["1. Entry Channels"]
        B2C["B2C Customer Storefront"]:::client
        M2M["External AI Buyer Agent"]:::client
        MerchantHub["Merchant Governance Hub"]:::client
    end

    subgraph GatewayLayer["2. FastAPI Application Gateway (:8000)"]
        DiscoveryAPI["Discovery Manifest (/.well-known/agent.json)"]:::gateway
        ChatAPI["Conversational API (/api/chat)"]:::gateway
        A2AAPI["A2A Protocol Gateway (/api/agent/*)"]:::gateway
        PaymentAPI["Razorpay Orders API (/api/create-order)"]:::gateway
    end

    subgraph CoreEngine["3. AI Reasoning & Governance Engine"]
        LLMParser["Heuristic & Intent Parser"]:::core
        ObjEngine["Merchant Objective Engine"]:::core
        PolicyEngine["Tripartite Policy Evaluator"]:::policy
        RiskGate["Risk Branching Engine"]:::policy
    end

    subgraph PaymentLayer["4. Settlement & Payments"]
        RZPOrder["Razorpay Orders API"]:::payment
        RZPModal["Checkout.js Web Modal"]:::payment
        HMACVerify["Server-side HMAC Verification"]:::payment
    end

    subgraph DataLayer["5. Authoritative Storage Layer"]
        SQLiteDB[("Append-Only SQLite Ledger")]:::storage
        DBTriggers["Database Engine Triggers"]:::storage
    end

    B2C --> ChatAPI
    B2C --> PaymentAPI
    M2M --> DiscoveryAPI
    M2M --> A2AAPI
    MerchantHub --> GatewayLayer

    ChatAPI --> LLMParser
    A2AAPI --> PolicyEngine
    LLMParser --> ObjEngine --> PolicyEngine
    
    PolicyEngine --> RiskGate
    RiskGate -->|"Safe (<= 10% Discount)"| PaymentAPI
    RiskGate -->|"High Risk (10% to 20% Discount)"| MerchantHub
    RiskGate -->|"Violation (> 20% Discount)"| B2C

    PaymentAPI --> RZPOrder --> RZPModal --> HMACVerify
    HMACVerify --> SQLiteDB
    GatewayLayer --> SQLiteDB
    DBTriggers -.-> SQLiteDB
```

---

## 2. Text-Based Architecture Layout

```text
+---------------------------------------------------------------------------------------------------------+
|                                        GROWTHPILOT AI ARCHITECTURE                                      |
+------------------------------------+------------------------------------+-------------------------------+
|        STOREFRONT (B2C)            |        EXTERNAL AI BUYERS (M2M)    |      MERCHANT HUB             |
|   • Natural language search        |   • Machine discovery (agent.json) |   • Strategic objective toggle|
|   • Objective-driven negotiation   |   • Redacted catalog feed          |   • Policy boundary controls  |
|   • Dynamic cross-sell / upsell    |   • HMAC-SHA256 signed mandates    |   • 1-Click approval queue    |
|   • Live Decision Inspector (7 Stg)|   • 2-Step Commit (Intent->Confirm)|   • Append-only SQLite audit  |
+-----------------+------------------+-----------------+------------------+---------------+---------------+
                  |                                    |                                  |
                  +------------------------------------+----------------------------------+
                                                       |
                                            [ FASTAPI GATEWAY :8000 ]
                                                       |
                          +----------------------------+----------------------------+
                          |                                                         |
              [ AI REASONING / HEURISTICS ]                             [ TRIPARTITE POLICY ENGINE ]
              • Natural language parser                                 • Hard Discount Cap (20%)
              • Dynamic objective injection                             • Unit Margin Floor (Rs.400)
              • Category accessory bundler                              • Max Qty Per SKU (5 units)
                          |                                             • Inventory Stock Check
                          +----------------------------+----------------------------+
                                                       |
                                        [ RISK GATE & BRANCHING ENGINE ]
                                                       |
                        +------------------------------+------------------------------+
                        |                              |                              |
                   [ APPROVED ]              [ WAITING FOR APPROVAL ]            [ BLOCKED ]
                 (Auto-Executed)               (Merchant Sign-off)            (Hard 409 Halt)
                        |                              |                              |
                        +------------------------------+------------------------------+
                                                       |
                                        [ RAZORPAY PAYMENT GATEWAY ]
                                        • Orders API (/api/create-order)
                                        • Checkout.js Standard Web Modal
                                        • HMAC-SHA256 Signature Verification
                                                       |
                                    [ APPEND-ONLY SQLITE AUDIT LEDGER ]
                                    • Database engine triggers prevent UPDATE/DELETE
                                    • Authoritative chronological trail (AUD-XXXX)
```

---

## 3. The 7-Stage Live Decision Telemetry Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / Agent
    participant AI as AI Engine
    participant Policy as Policy Gate
    participant Hub as Merchant Hub
    participant Ledger as SQLite Ledger

    Customer->>AI: 1. Customer Signal (Price objection / Search)
    AI->>AI: 2. Context Evaluated (Inject Active Objective)
    AI->>Policy: 3. Proposal Formulated (Discount / Bundle / Waiver)
    Policy->>Policy: 4. Policy Check (Margin Floor & Discount Cap)

    alt Safe Zone (<= 10% Discount)
        Policy->>Customer: 5. Risk: LOW -> Strategy Auto-Approved
    else Approval Gate (10% - 20% Discount)
        Policy->>Hub: 5. Risk: HIGH -> Queued for Merchant Sign-off
        Hub->>Policy: Revalidate Live Stock & Margin Floor
        Hub->>Customer: Approved & Checkout Unlocked
    else Hard Boundary Violation (> 20% Discount)
        Policy->>Customer: 5. Risk: BLOCKED -> HTTP 409 Graceful Explanation
    end

    Policy->>Ledger: 6. Action Execution
    Policy->>Ledger: 7. Commit Append-Only Audit Event (AUD-XXXX)
```

---

## 4. Machine-to-Machine (A2A) Commerce Sequence

```mermaid
sequenceDiagram
    autonumber
    actor BuyerAgent as External Autonomous Buyer Agent
    participant Manifest as /.well-known/agent.json
    participant Catalog as /api/agent/catalog
    participant Intent as /api/agent/checkout/intent
    participant Confirm as /api/agent/checkout/confirm
    participant Razorpay as Razorpay Orders API

    BuyerAgent->>Manifest: GET /.well-known/agent.json (Discovery)
    Manifest-->>BuyerAgent: Returns manifest (policy v1.0, endpoints, currencies)
    
    BuyerAgent->>Catalog: GET /api/agent/catalog?category=earbuds
    Catalog-->>BuyerAgent: Returns public catalog (cost prices redacted)
    
    BuyerAgent->>BuyerAgent: Construct Purchase Mandate & sign with HMAC-SHA256
    
    BuyerAgent->>Intent: POST /api/agent/checkout/intent { items, max_total, signature }
    
    alt Within Guardrails (Qty <= 5)
        Intent-->>BuyerAgent: HTTP 200 { intent_id: "int_xxx", status: "pending" }
        BuyerAgent->>Confirm: POST /api/agent/checkout/confirm { intent_id, signature }
        Confirm->>Razorpay: Create Payment Order
        Razorpay-->>Confirm: { razorpay_order_id: "order_xxx" }
        Confirm-->>BuyerAgent: HTTP 200 { status: "confirmed", razorpay_order_id }
    else Policy Violation (Qty > 5 Cap)
        Intent-->>BuyerAgent: HTTP 409 Conflict { status: "blocked", reason: "quantity_limit_exceeded", retry_suggestion: "Reduce quantity to 5 or fewer units." }
    end
```
