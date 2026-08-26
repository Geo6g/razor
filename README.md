# GrowthPilot AI 🚀
### Track 01: AI Growth & Agentic Commerce

GrowthPilot AI is a complete **Agentic Commerce & Autonomous Growth Engine** built on Razorpay test-mode APIs that **grows revenue for online merchants** and makes them **transactable by external AI buyers end-to-end**.

---

## 🎯 Track 01 Requirements & Feature Matrix

| Hackathon Requirement | GrowthPilot AI Implementation | Status |
| :--- | :--- | :---: |
| **Conversational In-App Checkout** | AI shopping agent parses customer intents, handles price objections with dynamic margin defense, initiates Razorpay checkout popups, and confirms orders with server-side signature verification. | ✅ Ready |
| **Agent-Readable Catalog & Manifest** | Implements `/.well-known/agent.json` discovery manifest and `/api/agent/catalog` feed stripping internal cost margins, optimized for LLM buyer agents. | ✅ Ready |
| **Agent-to-Agent (A2A) Commerce** | Standardized protocol support for **AP2** (Agent Payment Protocol), **ACP** (Agent Commerce Protocol), **x402** (HTTP 402 Payment Required standard), and **NPCI UAP** (Unified Agent Protocol). | ✅ Ready |
| **Cryptographic Mandates & Signing** | HMAC-SHA256 mandate signing and verification over canonical sorted JSON payloads with two-step commit (`intent` → `confirm`). | ✅ Ready |
| **Autonomous AI Buyer Agent** | Includes Python CLI buyer agent (`buyer_agent.py`) and an interactive **Live A2A Protocol Simulator** directly in the Merchant Hub web UI. | ✅ Ready |
| **Upsell & Cross-Sell Engine** | `/api/recommendations/upsell` dynamically generates complementary bundles, higher-tier upsells, and accessory pairings while enforcing positive profit margins. | ✅ Ready |
| **Campaign Orchestrator** | `/api/campaign/orchestrate` executes bounded multi-step campaigns for cart abandonment recovery, tiered price negotiations, high-AOV bundles, and returning customer reactivation. | ✅ Ready |
| **The Bar: Bounded, Gated & Explainable** | Every money action is bounded by merchant policy settings (Max discount cap %, Min profit margin preserved, Shipping fee waiver value). 5-stage explainable decision circuits. | ✅ Ready |
| **The Bar: Full Audit Trail** | Immutable SQLite ledger records every signal, policy check, cryptographic mandate, Razorpay order, and payment event. | ✅ Ready |
| **The Bar: Graceful Failure Handling** | **Scenario A**: Policy block for quantity cap breach (> 5 units) returns structured HTTP 409 with retry suggestions.<br>**Scenario B**: Payment card decline / abandonment is logged and recovered gracefully. | ✅ Ready |

---

## 🏗️ Architecture & Tech Stack

```text
growthpilot-ai/
├── frontend/                     # React 19 + Tailwind CSS + Recharts + Lucide
│   ├── src/
│   │   ├── App.jsx               # Storefront, Merchant Hub, A2A Studio, Campaigns Studio
│   │   └── index.css             # Tailwind styling & dark-mode theme
│   └── index.html                # Razorpay Checkout SDK integration
├── backend/                      # FastAPI Python Server
│   ├── data/
│   │   ├── catalog.json          # 15 electronics products with cost, price, and margins
│   │   └── growthpilot.db        # SQLite database with orders, audit logs, memory, settings
│   ├── db.py                     # SQLite helper functions, schema migrations, audit trail
│   ├── agent.py                  # AI Sales Assistant, Margin Defense Engine, Claude integration
│   ├── agent_buyer.py            # A2A Commerce Surface, AP2/ACP/UAP endpoints & signing
│   ├── payments.py               # Razorpay order creation and signature verification
│   └── main.py                   # REST API routes & static asset serving
├── buyer_agent.py                # Standalone Reference AI Buyer Agent (CLI)
├── app.py                        # Root launcher (runs FastAPI server on port 8000)
├── requirements.txt              # Python dependencies
└── README.md                     # Documentation
```

---

## ⚡ Setup & Run Instructions

### 1. Configure Credentials
Create or edit `.env` in the root workspace folder (copy from `.env.example`):
```env
# Optional: Falls back to built-in keyword parser if empty
CLAUDE_API_KEY=your_anthropic_api_key_here

# Razorpay Test Mode API Credentials (Required for payment gateway popups)
RAZORPAY_KEY_ID=rzp_test_your_key_id_here
RAZORPAY_KEY_SECRET=your_razorpay_secret_here

# Buyer agent shared secret for HMAC-SHA256 mandate signing
AGENT_BUYER_SECRET=your_shared_hmac_secret_here
```

### 2. Install Dependencies & Build Frontend
```bash
# Install Python packages
pip install -r requirements.txt

# Build the React frontend
cd frontend
npm install
npm run build
cd ..
```

### 3. Launch the Application
```bash
python app.py
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## 🎬 3-Minute Hackathon Demo Script

### Flow 1: Conversational AI Checkout & Margin Defense (Storefront)
1. Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** (Customer Storefront Mode).
2. Click **"🎧 Earbuds under 3000"** or type `Show me wireless earbuds`.
3. Click **"🏷️ Negotiate Deals"** or ask `Rs.4,999 seems too expensive for the SonicWave ANC Earbuds`.
4. Observe the **5-Stage AI Decision Lifecycle** and **Decision Card**:
   - High margin product → AI dynamically applies a 10% discount (`GROWTH10`) protecting ₹2,299 margin.
5. Click **"Confirm & Pay"** or type `confirm` → Razorpay checkout popup opens seamlessly.
6. Complete test payment or simulate card decline to demonstrate graceful failure handling.

### Flow 2: Autonomous AI Buyer Simulation (A2A Protocol Hub)
1. Switch to **Merchant Hub** → Click **"Agent-to-Agent (A2A)"** tab in sidebar.
2. Select **"Happy Path Purchase"** → Click **"Launch AI Buyer Agent"**:
   - Watch the agent discover manifest (`/.well-known/agent.json`), query catalog (`/api/agent/catalog`), sign HMAC-SHA256 mandate, pass policy check, create Razorpay order (`/api/agent/checkout/confirm`), and settle payment.
3. Select **"Policy Block (Quantity Cap)"** → Click **"Launch AI Buyer Agent"**:
   - Demonstrates **Graceful Failure**: AI Buyer requests 12 units (violating merchant limit of 5). Merchant policy evaluator intercepts and returns structured HTTP 409 with explainable retry suggestions.
4. Click **"Inspect Payload"** on any step to inspect the cryptographic signatures and JSON data.

### Flow 3: Autonomous Campaign Orchestrator & Upsell Engine
1. In Merchant Hub, click **"Campaigns & Upsell"** tab.
2. Select **"Abandoned Cart"** or **"Price Objection"** trigger:
   - Preview the bounded multi-step campaign plan with delay channels, policy constraints, and explainable copy.
3. In the **Upsell & Cross-Sell Studio**, select any catalog product and test recommendation modes (`Complementary Bundle`, `Higher-Tier Upsell`, `Compatible Accessories`):
   - Shows real-time protected profit margin calculations.

### Flow 4: Terminal CLI AI Buyer Execution
Judges can also run the reference AI buyer agent from their command line:
```bash
# Happy path AP2 purchase:
python buyer_agent.py

# Policy block graceful failure path (quantity cap breach):
python buyer_agent.py --block
```
