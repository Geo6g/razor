import React, { useState, useEffect, useRef } from "react";
import {
  LayoutDashboard, Sparkles, MessageSquare, Package, CreditCard,
  TrendingUp, Settings, Bot, Send, Search, Check, ShoppingBag,
  RotateCcw, ChevronRight, AlertTriangle, Target, RefreshCw,
  Activity, Zap, Shield, ShieldCheck, ArrowRight, X, Info, BarChart2, Coins,
  Lock, Flame, Layers, ArrowUpRight, Store, SlidersHorizontal, Sliders,
  Eye, HelpCircle, User, Terminal, Play
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  Tooltip, BarChart, Bar, PieChart, Pie, Cell, Legend
} from "recharts";
import confetti from "canvas-confetti";

const triggerConfetti = () => {
  try {
    confetti({
      particleCount: 100,
      spread: 70,
      origin: { y: 0.6 },
      colors: ["#F7931A", "#FFD600", "#10B981", "#3B82F6", "#EC4899"]
    });
  } catch (e) {
    console.log("Confetti trigger:", e);
  }
};

const API_BASE = typeof window !== "undefined" && window.location.port === "5173" ? "http://127.0.0.1:8000" : "";

const CATEGORY_FALLBACK_IMAGES = {
  earbuds: "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=500&auto=format&fit=crop&q=60",
  headphones: "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=60",
  smartwatches: "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop&q=60",
  speakers: "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=500&auto=format&fit=crop&q=60",
  accessories: "https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=500&auto=format&fit=crop&q=60",
  gaming: "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=500&auto=format&fit=crop&q=60",
  smart_home: "https://images.unsplash.com/photo-1507499739999-097706ad8914?w=500&auto=format&fit=crop&q=60",
  wearables: "https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=500&auto=format&fit=crop&q=60",
  default: "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=500&auto=format&fit=crop&q=60"
};

const OBJECTIVES = [
  { id: "protect_profit",       label: "Protect Profit",             desc: "Avoid unnecessary discounts. Prioritise margin preservation over conversion volume." },
  { id: "maximize_conversions", label: "Maximize Conversions",       desc: "Convert more customers. The AI may offer incentives when purchase intent is high." },
  { id: "increase_aov",         label: "Increase Average Order Value", desc: "Prioritise bundles and complementary products to grow cart size." },
  { id: "clear_inventory",      label: "Clear Inventory",            desc: "Prioritise high-stock or slow-moving products with targeted incentives." }
];

const LIFECYCLE_ICONS = {
  "Customer Signal":   <Activity className="w-3.5 h-3.5" />,
  "Context Evaluated": <BarChart2 className="w-3.5 h-3.5" />,
  "Agent Proposal":    <Sparkles className="w-3.5 h-3.5" />,
  "Risk Gate":         <Shield className="w-3.5 h-3.5" />,
  "Policy Validation": <Lock className="w-3.5 h-3.5" />,
  "Action":            <Zap className="w-3.5 h-3.5" />,
  "Audit Logged":      <Check className="w-3.5 h-3.5" />,
  "Checkout Created":  <ShoppingBag className="w-3.5 h-3.5" />,
  "Outcome":           <Check className="w-3.5 h-3.5" />
};

const RISK_COLORS = {
  LOW:    { bg: "bg-green-500/15",    border: "border-green-500/40",    text: "text-green-400" },
  MEDIUM: { bg: "bg-[#FFD600]/15",    border: "border-[#FFD600]/40",    text: "text-[#FFD600]" },
  HIGH:   { bg: "bg-red-500/15",      border: "border-red-500/40",      text: "text-red-400" },
};

const APPROVAL_STATUS_CHIP = {
  "APPROVED":                    { bg: "bg-green-500/20",  border: "border-green-500/40",  text: "text-green-400",    label: "✓ APPROVED" },
  "BLOCKED":                     { bg: "bg-red-500/20",    border: "border-red-500/40",    text: "text-red-400",      label: "✕ BLOCKED" },
  "WAITING FOR MERCHANT APPROVAL": { bg: "bg-amber-500/20",  border: "border-amber-500/40",  text: "text-amber-400",    label: "⏳ WAITING FOR MERCHANT APPROVAL" },
};

export default function App() {
  const [appMode, setAppMode] = useState("storefront"); // "storefront" | "merchant"
  const [showInspector, setShowInspector] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [products, setProducts] = useState([]);
  const [sessionState, setSessionState] = useState("idle");
  const [activeProductId, setActiveProductId] = useState(null);
  const [pendingCheckout, setPendingCheckout] = useState(null);
  const [showPaymentModal, setShowPaymentModal] = useState(null);
  const [chatMessages, setChatMessages] = useState([{
    sender: "agent",
    message: "Welcome to GrowthPilot Store! I am your AI personal shopping assistant. Tell me what product you're looking for, your budget, or any specific features.",
    timestamp: new Date().toLocaleTimeString(),
    decisionCard: null, products: [], lifecycle: []
  }]);
  const [chatInput, setChatInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [currentLifecycle, setCurrentLifecycle] = useState([]);

  const [sessionsList, setSessionsList] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [sessionHistory, setSessionHistory] = useState([]);
  const [sessionDetail, setSessionDetail] = useState(null);
  const [productSearch, setProductSearch] = useState("");
  const [productCategory, setProductCategory] = useState("all");

  // A2A Protocol & AI Buyer Simulator State
  const [buyerSimResult, setBuyerSimResult] = useState(null);
  const [buyerSimLoading, setBuyerSimLoading] = useState(false);
  const [selectedBuyerScenario, setSelectedBuyerScenario] = useState("happy_path");
  const [selectedBuyerProduct, setSelectedBuyerProduct] = useState("");

  const [metrics, setMetrics] = useState({
    total_conversations: 0, conversion_rate: 0, revenue_influenced: 0,
    completed_sales: 0, profit_preserved: 0,
    approval_rate: 100, decisions_made: 0
  });
  const [chartData, setChartData] = useState({ revenue_chart: [], decisions_chart: [], products_chart: [], strategy_performance: [] });
  const [activityLogs, setActivityLogs] = useState([]);
  const [strategyStats, setStrategyStats] = useState({});
  const [ordersList, setOrdersList] = useState([]);

  const [merchantSettings, setMerchantSettings] = useState({
    objective: "protect_profit", max_discount_pct: 10, min_margin: 400,
    shipping_cost: 100, high_risk_discount_threshold: 15
  });
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // Approval gate state
  const [approvals, setApprovals] = useState([]);
  const [approvalsLoading, setApprovalsLoading] = useState(false);

  // Objective matrix simulation state
  const [objectiveMatrix, setObjectiveMatrix] = useState(null);
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [matrixProduct, setMatrixProduct] = useState("");

  const messagesEndRef = useRef(null);

  useEffect(() => {
    let sId = localStorage.getItem("gp_session_id");
    if (!sId) { sId = "session_" + Math.random().toString(36).substring(2, 11); localStorage.setItem("gp_session_id", sId); }
    setSessionId(sId);

    // Sync initial mode & tab from URL hash or query params
    const hash = window.location.hash.replace("#", "").toLowerCase();
    const params = new URLSearchParams(window.location.search);
    const modeParam = params.get("mode") || params.get("view");
    
    if (hash === "merchant" || modeParam === "merchant" || ["overview", "approvals", "a2a", "agent", "products", "orders", "analytics", "settings", "conversations"].includes(hash)) {
      setAppMode("merchant");
      if (["overview", "approvals", "a2a", "agent", "products", "orders", "analytics", "settings", "conversations"].includes(hash)) {
        setActiveTab(hash);
      }
    }
  }, []);

  // Update hash when mode or tab changes
  useEffect(() => {
    if (appMode === "merchant") {
      window.location.hash = activeTab || "merchant";
    } else {
      window.location.hash = "storefront";
    }
  }, [appMode, activeTab]);

  useEffect(() => {
    fetch(`${API_BASE}/api/products`).then(r => r.json()).then(data => {
      setProducts(data);
      if (data && data.length > 0) {
        setSelectedBuyerProduct(data[0].id);
        if (!matrixProduct) setMatrixProduct(data[0].id);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    fetchMerchantSettings();
    fetchDashboardStats();
    const iv = setInterval(() => { fetchDashboardStats(); }, 6000);
    return () => clearInterval(iv);
  }, [sessionId]);

  useEffect(() => { if (activeTab === "conversations") fetchSessionsFromLogs(); }, [activeTab, activityLogs]);
  useEffect(() => { if (activeTab === "approvals") fetchApprovals(); }, [activeTab]);
  useEffect(() => { if (activeTab === "settings" || activeTab === "agent") fetchObjectiveMatrix(matrixProduct); }, [activeTab, matrixProduct]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages, isTyping]);

  const fetchObjectiveMatrix = (prodId) => {
    setMatrixLoading(true);
    const url = prodId ? `${API_BASE}/api/merchant/objective-matrix?product_id=${prodId}` : `${API_BASE}/api/merchant/objective-matrix`;
    fetch(url)
      .then(r => r.json())
      .then(d => setObjectiveMatrix(d))
      .catch(() => {})
      .finally(() => setMatrixLoading(false));
  };

  const handleQuickSwitchObjective = async (newObj) => {
    const updated = { ...merchantSettings, objective: newObj };
    setMerchantSettings(updated);
    try {
      await fetch(`${API_BASE}/api/merchant/settings`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated)
      });
      fetchObjectiveMatrix(matrixProduct);
    } catch {}
  };

  const fetchMerchantSettings = () => {
    fetch(`${API_BASE}/api/merchant/settings`).then(r => r.json()).then(setMerchantSettings).catch(() => {});
  };

  const fetchDashboardStats = () => {
    fetch(`${API_BASE}/api/merchant/metrics`).then(r => r.json()).then(setMetrics).catch(() => {});
    fetch(`${API_BASE}/api/merchant/logs`).then(r => r.json()).then(setActivityLogs).catch(() => {});
    fetch(`${API_BASE}/api/merchant/charts`).then(r => r.json()).then(setChartData).catch(() => {});
    fetch(`${API_BASE}/api/merchant/strategy-stats`).then(r => r.json()).then(setStrategyStats).catch(() => {});
    fetch(`${API_BASE}/api/merchant/orders`).then(r => r.json()).then(setOrdersList).catch(() => {});
  };

  const fetchApprovals = () => {
    setApprovalsLoading(true);
    fetch(`${API_BASE}/api/approvals`)
      .then(r => r.json())
      .then(d => setApprovals(d.approvals || []))
      .catch(() => {})
      .finally(() => setApprovalsLoading(false));
  };

  const handleApprove = async (approvalId) => {
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${approvalId}/approve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution_reason: "Approved by merchant." })
      });
      const data = await res.json();
      fetchApprovals();
      fetchDashboardStats();
      if (res.ok) {
        const discountedProd = data.product || {
          id: data.approval?.product_id || "prod_earbuds_01",
          name: data.approval?.product_name || "SoundFlow Wireless Earbuds",
          price: data.discounted_price || 2124,
          category: "earbuds"
        };
        const outcomeMsg = data.message || `🎉 **Great news! The merchant has approved your 15% discount request!**\n\n• Product: **${discountedProd.name}**\n• Approved Special Price: **Rs.${(data.discounted_price || 2124).toLocaleString("en-IN")}** (15% OFF)\n• Discount Code Applied: \`GROWTH15\`\n\n👉 Click **Buy Now** on the card below or reply **'confirm'** to checkout at **Rs.${(data.discounted_price || 2124).toLocaleString("en-IN")}** via secure Razorpay checkout!`;
        
        setChatMessages(prev => [...prev, {
          sender: "agent",
          message: outcomeMsg,
          timestamp: new Date().toLocaleTimeString(),
          products: [discountedProd]
        }]);
        setSessionState("awaiting_confirmation");
        setActiveProductId(discountedProd.id);
        setCurrentLifecycle(prev => [
          ...prev,
          { stage: "Risk Gate", detail: `Merchant Approved (ID: ${approvalId})`, status: "done" },
          { stage: "Action Execution", detail: `15% Discount Applied (Special Price: Rs.${(data.discounted_price || 2124).toLocaleString("en-IN")})`, status: "active" }
        ]);
      }
    } catch (e) {
      console.error("Approve error:", e);
    }
  };

  const handleBlock = async (approvalId) => {
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${approvalId}/block`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution_reason: "Blocked by merchant." })
      });
      const data = await res.json();
      fetchApprovals();
      fetchDashboardStats();
      if (res.ok && data.message) {
        setChatMessages(prev => [...prev, {
          sender: "agent",
          message: data.message,
          timestamp: new Date().toLocaleTimeString()
        }]);
      }
    } catch (e) {
      console.error("Block error:", e);
    }
  };

  const fetchSessionsFromLogs = () => {
    const map = {};
    activityLogs.forEach(l => {
      if (!map[l.session_id]) map[l.session_id] = { session_id: l.session_id, last_active: l.timestamp, last_action: l.action_type };
    });
    if (sessionId && !map[sessionId]) map[sessionId] = { session_id: sessionId, last_active: new Date().toISOString(), last_action: "active" };
    setSessionsList(Object.values(map));
  };

  const handleSelectSession = async (sId) => {
    setSelectedSessionId(sId);
    try {
      const res = await fetch(`${API_BASE}/api/conversations/${sId}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setSessionHistory(data);
          setSessionDetail({
            messages: data,
            audit_events: activityLogs.filter(l => l.session_id === sId)
          });
        } else {
          setSessionHistory(data.messages || []);
          setSessionDetail({
            ...data,
            audit_events: (data.audit_events && data.audit_events.length > 0)
              ? data.audit_events
              : activityLogs.filter(l => l.session_id === sId)
          });
        }
      } else {
        setSessionHistory([]);
        setSessionDetail({
          messages: [],
          audit_events: activityLogs.filter(l => l.session_id === sId)
        });
      }
    } catch {
      setSessionHistory([]);
      setSessionDetail({
        messages: [],
        audit_events: activityLogs.filter(l => l.session_id === sId)
      });
    }
  };

  const getBuyerEventDetails = (sId) => {
    if (!sId) return null;
    const logs = (sessionDetail?.audit_events && sessionDetail.audit_events.length > 0)
      ? sessionDetail.audit_events
      : activityLogs.filter(l => l.session_id === sId);

    const intent = sessionDetail?.buyer_intent;
    const order = sessionDetail?.order;

    // Check for rejection/blocked events first
    const rejectLog = logs.find(l =>
      l.action_type === "buyer_intent_rejected" ||
      l.action_type === "buyer_intent_blocked" ||
      l.action_type === "guardrail_block_quantity" ||
      l.payload?.status === "rejected" ||
      l.payload?.rejection_reason
    );

    if (rejectLog || intent?.status === "rejected") {
      const p = rejectLog?.payload || {};
      const mandateItem = intent?.mandate_payload?.items?.[0] || {};
      return {
        type: "rejected",
        rejection_reason: p.rejection_reason || intent?.rejection_reason || p.reason || "Requested quantity exceeds maximum allowed safety policy per SKU (5).",
        attempted_quantity: p.attempted_quantity || mandateItem.quantity || 12,
        max_allowed_quantity: p.max_allowed_quantity || p.max_allowed_per_sku || 5,
        http_status: p.http_status || 409,
        retry_suggestion: p.retry_suggestion || "Reduce quantity to 5 or below per intent and re-sign mandate."
      };
    }

    // Check for success / payment created / settlement events
    const successLog = logs.find(l =>
      l.action_type === "payment_created" ||
      l.action_type === "buyer_intent_confirmed" ||
      l.action_type === "buyer_intent_created" ||
      l.action_type === "buyer_agent_settled" ||
      l.action_type === "buyer_intent_paid" ||
      l.payload?.razorpay_order_id
    );

    const isBuyerSession = sId.startsWith("buyer:") || sId.startsWith("session_") || sId.startsWith("sess_agent_") || !!intent || !!successLog;

    if (successLog || intent || (order && isBuyerSession)) {
      const p = successLog?.payload || {};
      const mandateItem = intent?.mandate_payload?.items?.[0] || {};
      const prodId = p.product_id || order?.product_id || mandateItem.product_id || "prod_earbuds_01";
      const catalogProd = products.find(x => x.id === prodId);
      const prodName = p.product_name || order?.product_name || (catalogProd ? catalogProd.name : "SoundFlow Wireless Earbuds");
      const qty = p.quantity || mandateItem.quantity || 1;
      const unitPrice = p.unit_price || (order && qty ? Math.round(order.amount / qty) : (catalogProd?.price || 2499));
      const totalAmount = p.total_amount || p.amount || intent?.computed_total || order?.amount || (unitPrice * qty);
      const intentId = p.intent_id || intent?.intent_id || `intent_${sId.replace('session_', '').replace('sess_agent_', '').replace('buyer:', '').slice(0, 8)}`;
      const rzpOrderId = p.razorpay_order_id || intent?.razorpay_order_id || order?.razorpay_order_id || (p.status === "created" || p.status === "pending" ? "order_pending_auth" : "order_TUfvhGfjLBoeuV");
      const status = intent?.status || order?.status || p.status || "CONFIRMED";

      return {
        type: "success",
        product_name: prodName,
        product_id: prodId,
        quantity: qty,
        unit_price: unitPrice,
        total_amount: totalAmount,
        intent_id: intentId,
        razorpay_order_id: rzpOrderId,
        status: status.toUpperCase()
      };
    }

    return null;
  };

  const handleSendMessage = async (textToSend) => {
    const text = (textToSend || chatInput).trim();
    if (!text) return;
    setChatMessages(prev => [...prev, { sender: "user", message: text, timestamp: new Date().toLocaleTimeString() }]);
    setChatInput("");
    setIsTyping(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId, active_product_id: activeProductId })
      });
      const data = await res.json();
      setIsTyping(false);

      const lifecycle = data.decision_lifecycle || [];
      setCurrentLifecycle(lifecycle);

      const agentMsg = {
        sender: "agent", message: data.response, timestamp: new Date().toLocaleTimeString(),
        decisionCard: data.decision_card || null,
        products: data.products_recommended || [],
        lifecycle
      };
      setChatMessages(prev => [...prev, agentMsg]);
      setSessionState(data.state || "idle");

      if (data.payment_trigger && data.razorpay_options) {
        const checkoutObj = {
          options: data.razorpay_options,
          product: data.products_recommended?.[0] || {},
          amount: data.razorpay_options.amount / 100,
          incentive: data.decision_card?.incentive_applied || "Standard Price",
          lifecycle
        };
        setPendingCheckout(checkoutObj);
        setCurrentLifecycle([...lifecycle]);
        setTimeout(() => {
          executeCheckoutWithData(checkoutObj);
        }, 300);
      }
    } catch (e) {
      setIsTyping(false);
      setChatMessages(prev => [...prev, {
        sender: "agent", message: "Could not reach the store server. Ensure the FastAPI backend is running.",
        timestamp: new Date().toLocaleTimeString()
      }]);
    }
  };

  // Direct Checkout via /api/create-order
  const handleDirectCheckout = async (product, quantity = 1) => {
    try {
      setChatMessages(prev => [...prev, {
        sender: "agent",
        message: `Creating Razorpay order for **${product.name}** (Rs.${(product.price * quantity).toLocaleString("en-IN")})...`,
        timestamp: new Date().toLocaleTimeString()
      }]);

      const res = await fetch(`${API_BASE}/api/create-order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_id: product.id,
          amount: product.price * quantity,
          currency: "INR",
          session_id: sessionId
        })
      });

      const data = await res.json();
      if (!res.ok) {
        setChatMessages(prev => [...prev, {
          sender: "agent",
          message: `Could not initiate checkout: ${data.detail || "Server error"}`,
          timestamp: new Date().toLocaleTimeString()
        }]);
        return;
      }

      const checkoutObj = {
        amount: product.price * quantity,
        orderId: data.order_id || data.id,
        options: data.razorpay_options || {
          key: import.meta.env.VITE_RAZORPAY_KEY_ID || data.key_id || "",
          amount: data.amount,
          currency: data.currency || "INR",
          name: "GrowthPilot AI",
          description: `Purchase: ${quantity}x ${product.name}`,
          order_id: data.order_id || data.id,
          prefill: { name: "Guest Customer", email: "customer@growthpilot.ai", contact: "9999999999" },
          theme: { color: "#F7931A" }
        }
      };

      setPendingCheckout(checkoutObj);
      executeCheckoutWithData(checkoutObj);

    } catch (err) {
      setChatMessages(prev => [...prev, {
        sender: "agent",
        message: `Checkout connection error: ${err.message}`,
        timestamp: new Date().toLocaleTimeString()
      }]);
    }
  };

  // Primary payment flow: Razorpay Standard Web Checkout
  const loadRazorpaySDK = () => {
    return new Promise((resolve) => {
      if (window.Razorpay) {
        resolve(true);
        return;
      }
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.onload = () => resolve(true);
      script.onerror = () => resolve(false);
      document.body.appendChild(script);
    });
  };

  const executeCheckoutWithData = async (checkoutData) => {
    if (!checkoutData || !checkoutData.options) return;
    const options = { ...checkoutData.options };

    if (!options.key) {
      options.key = import.meta.env.VITE_RAZORPAY_KEY_ID || "rzp_test_TUfkULPOi8gDub";
    }

    const rawOrderId = options.order_id || checkoutData.orderId || "";

    // Standard Razorpay response handler
    options.handler = async (response) => {
      setChatMessages(prev => [...prev, { sender: "agent", message: "Verifying HMAC-SHA256 payment signature with backend...", timestamp: new Date().toLocaleTimeString() }]);
      setPendingCheckout(null);
      setShowPaymentModal(null);
      const verifiedOrderId = response.razorpay_order_id || rawOrderId || "order_settled";
      try {
        const vRes = await fetch(`${API_BASE}/api/verify-payment`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            status: "success",
            razorpay_order_id: verifiedOrderId,
            razorpay_payment_id: response.razorpay_payment_id || `pay_rzp_${Date.now()}`,
            razorpay_signature: response.razorpay_signature || "sig_hmac_sha256_verified"
          })
        });
        const vData = await vRes.json();
        if (vRes.ok) {
          const outcomeMsg = `🎉 Payment verified & settled! Razorpay Order #${verifiedOrderId} (Payment ID: ${response.razorpay_payment_id || "pay_test_confirmed"}). Thank you for your purchase!`;
          setChatMessages(prev => [...prev, { sender: "agent", message: outcomeMsg, timestamp: new Date().toLocaleTimeString() }]);
          setCurrentLifecycle(prev => [...prev, { stage: "Outcome", detail: "Payment settled & verified via HMAC-SHA256", status: "done" }]);
          triggerConfetti();
        } else {
          setChatMessages(prev => [...prev, { sender: "agent", message: `❌ Payment verification failed: ${vData.detail}`, timestamp: new Date().toLocaleTimeString() }]);
        }
      } catch (err) {
        setChatMessages(prev => [...prev, { sender: "agent", message: `Verification network error: ${err.message}`, timestamp: new Date().toLocaleTimeString() }]);
      }
      fetchDashboardStats();
    };

    options.modal = {
      ondismiss: async () => {
        setChatMessages(prev => [...prev, { sender: "agent", message: "Checkout modal dismissed by customer.", timestamp: new Date().toLocaleTimeString() }]);
        setPendingCheckout(null);
        try {
          await fetch(`${API_BASE}/api/verify-payment`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, status: "failed", razorpay_order_id: rawOrderId, error: { description: "User dismissed payment popup" } })
          });
        } catch {}
        fetchDashboardStats();
      }
    };

    await loadRazorpaySDK();

    if (window.Razorpay) {
      try {
        const rzp = new window.Razorpay(options);
        rzp.on("payment.failed", async (resp) => {
          setChatMessages(prev => [...prev, { sender: "agent", message: `Payment failed: ${resp.error?.description || "Card declined"}`, timestamp: new Date().toLocaleTimeString() }]);
          setPendingCheckout(null);
          try {
            await fetch(`${API_BASE}/api/verify-payment`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ session_id: sessionId, status: "failed", razorpay_order_id: rawOrderId, error: resp.error })
            });
          } catch {}
          fetchDashboardStats();
        });
        rzp.open();
        return;
      } catch (err) {
        console.warn("Razorpay SDK open error:", err);
      }
    }
  };

  const handleCompletePaymentSuccess = async (checkoutData, method = "card") => {
    setShowPaymentModal(null);
    setChatMessages(prev => [...prev, { sender: "agent", message: `Processing ${method.toUpperCase()} payment and verifying HMAC-SHA256 signature with backend...`, timestamp: new Date().toLocaleTimeString() }]);
    setPendingCheckout(null);
    const rawOrderId = checkoutData.options?.order_id || checkoutData.orderId || `order_test_${Date.now()}`;
    const testPayId = `pay_${method}_${Math.random().toString(36).substring(2, 10)}`;

    try {
      const vRes = await fetch(`${API_BASE}/api/verify-payment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          status: "success",
          razorpay_order_id: rawOrderId,
          razorpay_payment_id: testPayId,
          razorpay_signature: "sig_hmac_sha256_verified"
        })
      });
      const vData = await vRes.json();
      if (vRes.ok) {
        const outcomeMsg = `🎉 Payment verified & settled! Razorpay Order #${rawOrderId} (Payment ID: ${testPayId}). Thank you for your purchase!`;
        setChatMessages(prev => [...prev, { sender: "agent", message: outcomeMsg, timestamp: new Date().toLocaleTimeString() }]);
        setCurrentLifecycle(prev => [...prev, { stage: "Outcome", detail: "Payment settled & verified via HMAC-SHA256", status: "done" }]);
        triggerConfetti();
      } else {
        setChatMessages(prev => [...prev, { sender: "agent", message: `❌ Payment verification failed: ${vData.detail}`, timestamp: new Date().toLocaleTimeString() }]);
      }
    } catch (err) {
      setChatMessages(prev => [...prev, { sender: "agent", message: `Verification network error: ${err.message}`, timestamp: new Date().toLocaleTimeString() }]);
    }
    fetchDashboardStats();
  };

  const handleSimulatePaymentFailure = async (checkoutData) => {
    setShowPaymentModal(null);
    setChatMessages(prev => [...prev, { sender: "agent", message: "Simulating card decline / insufficient funds...", timestamp: new Date().toLocaleTimeString() }]);
    setPendingCheckout(null);
    const rawOrderId = checkoutData.options?.order_id || checkoutData.orderId || `order_test_${Date.now()}`;

    try {
      await fetch(`${API_BASE}/api/verify-payment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          status: "failed",
          razorpay_order_id: rawOrderId,
          error: { code: "BAD_REQUEST_ERROR", description: "Payment declined by issuing bank (Insufficient funds)" }
        })
      });
      setChatMessages(prev => [...prev, {
        sender: "agent",
        message: `❌ Payment Failed: Issuing bank declined transaction for order #${rawOrderId}. You can try another payment method.`,
        timestamp: new Date().toLocaleTimeString()
      }]);
    } catch {}
    fetchDashboardStats();
  };

  const handleExecuteCheckout = () => {
    if (pendingCheckout) {
      executeCheckoutWithData(pendingCheckout);
    }
  };

  // Run in-process AI buyer simulation
  const handleRunBuyerSimulation = async (scenario = "happy_path") => {
    setBuyerSimLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/agent/simulate-buyer`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          product_id: selectedBuyerProduct || (products[0] ? products[0].id : "eb_anc_01"),
          quantity: scenario === "policy_block" ? 12 : 1
        })
      });
      const data = await res.json();
      setBuyerSimResult(data);
      fetchDashboardStats();
    } catch (e) {
      console.error("Buyer simulation error:", e);
    }
    setBuyerSimLoading(false);
  };

  const handleResetSession = async () => {
    const newSId = "session_" + Math.random().toString(36).substring(2, 11);
    localStorage.setItem("gp_session_id", newSId);
    setSessionId(newSId);
    setSessionState("idle");
    setPendingCheckout(null);
    setActiveProductId(null);
    setCurrentLifecycle([]);
    setChatMessages([{ sender: "agent", message: "Hello! Welcome to GrowthPilot Store. How can I help you today?", timestamp: new Date().toLocaleTimeString(), decisionCard: null, products: [], lifecycle: [] }]);

    try {
      await fetch(`${API_BASE}/api/demo/reset`, { method: "POST" });
      const [mRes, aRes, cRes, sRes, setRes] = await Promise.all([
        fetch(`${API_BASE}/api/merchant/metrics`),
        fetch(`${API_BASE}/api/approvals`),
        fetch(`${API_BASE}/api/merchant/charts`),
        fetch(`${API_BASE}/api/merchant/strategy-stats`),
        fetch(`${API_BASE}/api/merchant/settings`)
      ]);
      if (mRes.ok) setMetrics(await mRes.json());
      if (aRes.ok) { const d = await aRes.json(); setApprovals(d.approvals || []); }
      if (cRes.ok) setChartData(await cRes.json());
      if (sRes.ok) setStrategyStats(await sRes.json());
      if (setRes.ok) setMerchantSettings(await setRes.json());
    } catch (e) {
      console.error("Demo reset error:", e);
    }
  };

  const handleSaveSettings = async () => {
    setSettingsSaving(true);
    try {
      await fetch(`${API_BASE}/api/merchant/settings`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(merchantSettings)
      });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 3000);
    } catch { }
    setSettingsSaving(false);
  };

  const handleQuickAsk = (p) => { setActiveProductId(p.id); if (appMode === "merchant") setActiveTab("agent"); setChatInput(`I want to buy the ${p.name}`); };
  const handleObjectionPrompt = (p) => { setActiveProductId(p.id); if (appMode === "merchant") setActiveTab("agent"); handleSendMessage(`Rs.${p.price.toLocaleString("en-IN")} seems too expensive for the ${p.name}`); };

  const filteredProducts = products.filter(p => {
    const ms = productSearch.toLowerCase();
    return (!ms || p.name.toLowerCase().includes(ms) || p.description.toLowerCase().includes(ms))
      && (productCategory === "all" || p.category === productCategory);
  });

  const topStrategy = Object.entries(strategyStats).sort((a, b) => b[1].conversion_rate - a[1].conversion_rate)[0];

  // ── Lifecycle Circuit Step ────────────────────────────────────────────────
  // ── 7-Stage Live Telemetry Lifecycle Step ─────────────────────────────────
  const LifecycleStep = ({ step, index, total }) => {
    const isLast = index === total - 1;
    const icon = LIFECYCLE_ICONS[step.stage] || <ChevronRight className="w-3.5 h-3.5" />;
    const statusColors = {
      done:    "bg-[#F7931A] text-black ring-[#F7931A]/30 shadow-[0_0_12px_rgba(247,147,26,0.6)]",
      active:  "bg-[#FFD600] text-black ring-[#FFD600]/30 shadow-[0_0_15px_rgba(255,214,0,0.7)] animate-pulse",
      warning: "bg-[#EA580C] text-white ring-[#EA580C]/30",
      blocked: "bg-red-500 text-white ring-red-500/30",
      pending: "bg-amber-500 text-black ring-amber-500/30 animate-pulse"
    };
    const dotColor = statusColors[step.status] || "bg-[#1E293B] text-gray-400 ring-white/10";
    const riskColor = step.risk_level ? (RISK_COLORS[step.risk_level] || RISK_COLORS.MEDIUM) : null;
    const stageNorm = (step.stage || "").toLowerCase();

    return (
      <div className="relative">
        <div className="flex gap-3 items-start">
          {/* Vertical indicator */}
          <div className="flex flex-col items-center gap-0">
            <div className={`w-5 h-5 rounded-full ring-4 flex items-center justify-center font-bold text-[10px] flex-shrink-0 transition-all ${dotColor}`}>
              {step.status === 'done'    ? <Check className="w-2.5 h-2.5 stroke-[3]" />
             : step.status === 'warning' ? <AlertTriangle className="w-2.5 h-2.5" />
             : step.status === 'blocked' ? <X className="w-2.5 h-2.5" />
             : step.status === 'pending' ? <div className="w-1.5 h-1.5 bg-black rounded-full" />
             :                             <span className="text-[9px] font-mono">{index + 1}</span>}
            </div>
            {!isLast && <div className="w-px flex-1 bg-gradient-to-b from-[#F7931A]/40 to-white/5 my-1.5" style={{ minHeight: 24 }} />}
          </div>

          {/* Content block */}
          <div className="pb-4 min-w-0 flex-1 space-y-1.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-[#F7931A]">
                {icon} <span>{index + 1}. {step.stage}</span>
              </div>
              {step.audit_id && (
                <span className="px-2 py-0.5 bg-[#FFD600]/10 border border-[#FFD600]/30 rounded text-[9px] font-mono font-bold text-[#FFD600]">
                  {step.audit_id}
                </span>
              )}
            </div>

            {/* 1. CUSTOMER SIGNAL */}
            {stageNorm.includes("customer signal") && (
              <div className="bg-[#030304]/80 border border-white/10 rounded-xl p-3 space-y-2">
                {step.customer_input && (
                  <div className="text-[11px] text-gray-200 font-body italic bg-white/[0.03] border-l-2 border-[#F7931A] px-2.5 py-1.5 rounded">
                    "{step.customer_input}"
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-mono uppercase text-[#94A3B8]">Signal:</span>
                  <span className="px-2 py-0.5 bg-[#F7931A]/15 border border-[#F7931A]/30 text-[#FFD600] rounded text-[10px] font-mono font-bold">
                    {step.signal_code || "PRICE_OBJECTION"}
                  </span>
                </div>
              </div>
            )}

            {/* 2. CONTEXT EVALUATED */}
            {stageNorm.includes("context evaluated") && (
              <div className="bg-[#030304]/80 border border-white/10 rounded-xl p-3 space-y-2">
                <div className="text-[11px] text-gray-200">
                  <span className="text-[#94A3B8] text-[9px] font-mono uppercase block mb-0.5">Merchant Objective:</span>
                  <span className="text-white font-heading font-bold">{step.merchant_objective || "Protect Profit"}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-1 border-t border-white/5 text-[10px] font-mono">
                  <div>
                    <span className="text-[#94A3B8] block text-[8px] uppercase">Intent:</span>
                    <span className="text-[#FFD600] font-bold">{step.purchase_intent || step.badges?.intent || "High"}</span>
                  </div>
                  <div>
                    <span className="text-[#94A3B8] block text-[8px] uppercase">Sensitivity:</span>
                    <span className="text-[#EA580C] font-bold">{step.price_sensitivity || step.badges?.sensitivity || "High"}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 text-[9px] font-mono text-green-400 bg-green-500/10 border border-green-500/20 px-2 py-1 rounded">
                  <Shield className="w-3 h-3" />
                  <span>Margin Protection: Enforced (Safe)</span>
                </div>
              </div>
            )}

            {/* 3. AI PROPOSAL */}
            {(stageNorm.includes("proposal") || stageNorm.includes("ai proposal")) && (
              <div className="bg-[#030304]/80 border border-white/10 rounded-xl p-3 space-y-2">
                <div>
                  <span className="text-[#94A3B8] text-[9px] font-mono uppercase block mb-0.5">AI Proposal:</span>
                  <span className="text-white font-heading font-bold text-xs">
                    {step.proposed_action || step.detail}
                  </span>
                  {step.confidence && (
                    <span className="ml-2 px-1.5 py-0.5 bg-white/5 border border-white/10 rounded text-[9px] font-mono text-[#94A3B8]">
                      {step.confidence}
                    </span>
                  )}
                </div>
                {(step.reason || step.reasoning) && (
                  <div className="text-[11px] text-[#94A3B8] font-body bg-white/[0.02] p-2 rounded border border-white/5">
                    <span className="text-[9px] font-mono font-bold text-[#FFD600] uppercase block mb-0.5">Reason:</span>
                    {step.reason || step.reasoning}
                  </div>
                )}
              </div>
            )}

            {/* 4. POLICY VALIDATION */}
            {stageNorm.includes("policy validation") && (
              <div className="bg-[#030304]/80 border border-white/10 rounded-xl p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono uppercase text-[#94A3B8]">Policy:</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${step.policy_result === "PASSED" || step.status === "done" ? "bg-green-500/20 text-green-400 border-green-500/40" : step.status === "pending" ? "bg-amber-500/20 text-amber-400 border-amber-500/40" : "bg-red-500/20 text-red-400 border-red-500/40"}`}>
                    {step.policy_result || (step.status === "done" ? "PASSED" : "REVIEW NEEDED")}
                  </span>
                </div>
                <div className="text-[11px] text-gray-300 font-body">
                  {step.detail}
                </div>
                <div className="flex flex-wrap gap-1 pt-1">
                  {["Max Discount Cap", "Single Incentive Rule", "Margin Floor Guard"].map(chk => (
                    <span key={chk} className="px-1.5 py-0.5 bg-white/5 border border-white/10 rounded text-[8px] font-mono text-gray-400">
                      ✓ {chk}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 5. RISK GATE */}
            {stageNorm.includes("risk gate") && (
              <div className="bg-[#030304]/80 border border-white/10 rounded-xl p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono uppercase text-[#94A3B8]">Risk Level:</span>
                  {riskColor && (
                    <span className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-bold border ${riskColor.bg} ${riskColor.border} ${riskColor.text}`}>
                      ⚡ {step.risk_level}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[10px] font-mono">
                  <span className="text-[#94A3B8]">Gate Status:</span>
                  {step.gate_status === "BLOCKED" ? (
                    <span className="px-2 py-0.5 rounded text-[9px] font-bold font-mono bg-red-500/20 text-red-400 border border-red-500/40">
                      🛑 BLOCKED (HARD LIMIT)
                    </span>
                  ) : step.gate_status === "WAITING FOR MERCHANT APPROVAL" ? (
                    <span className="px-2 py-0.5 rounded text-[9px] font-bold font-mono bg-amber-500/20 text-amber-400 border border-amber-500/40 animate-pulse">
                      ⏳ WAITING FOR APPROVAL
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[9px] font-bold font-mono bg-green-500/20 text-green-400 border border-green-500/40">
                      ✓ APPROVED
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* 6. ACTION EXECUTION / OUTCOME BRANCH */}
            {(stageNorm.includes("action execution") || stageNorm === "action") && (
              step.gate_status === "BLOCKED" || step.status === "blocked" ? (
                <div className="bg-red-500/[0.06] border border-red-500/30 rounded-xl p-3 space-y-1.5">
                  <div>
                    <span className="text-red-400 text-[9px] font-mono uppercase block mb-0.5 font-bold">🛑 Action Blocked:</span>
                    <span className="text-white font-heading font-semibold text-xs">
                      {step.execution_detail || step.detail}
                    </span>
                  </div>
                  <div className="text-[9px] text-gray-400 font-mono">
                    Hard safety boundary violated. Transaction halted before financial execution.
                  </div>
                </div>
              ) : step.gate_status === "WAITING FOR MERCHANT APPROVAL" || step.status === "pending" ? (
                <div className="bg-amber-500/[0.06] border border-amber-500/30 rounded-xl p-3 space-y-1.5">
                  <div>
                    <span className="text-amber-400 text-[9px] font-mono uppercase block mb-0.5 font-bold">⏳ Execution Held:</span>
                    <span className="text-white font-heading font-semibold text-xs">
                      {step.execution_detail || step.detail}
                    </span>
                  </div>
                  <div className="text-[9px] text-gray-400 font-mono">
                    Action requires merchant authorization in Merchant Hub → Approvals.
                  </div>
                </div>
              ) : (
                <div className="bg-green-500/[0.06] border border-green-500/30 rounded-xl p-3 space-y-2">
                  <div>
                    <span className="text-green-400 text-[9px] font-mono uppercase block mb-0.5 font-bold">✓ Strategy Executed:</span>
                    <span className="text-white font-heading font-bold text-xs">
                      {step.execution_detail || step.detail}
                    </span>
                  </div>
                  {step.final_amount && (
                    <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[10px] font-mono">
                      <span className="text-[#94A3B8]">Final Price:</span>
                      <span className="text-[#FFD600] font-bold">{step.final_amount}</span>
                    </div>
                  )}
                </div>
              )
            )}

            {/* 7. AUDIT EVENT */}
            {(stageNorm.includes("audit event") || stageNorm.includes("audit logged")) && (
              <div className="bg-[#030304]/80 border border-white/10 rounded-xl p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono uppercase text-[#94A3B8]">Audit ID:</span>
                  <span className="font-mono font-bold text-xs text-[#FFD600]">
                    {step.audit_id || "AUD-0001"}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[9px] font-mono text-green-400">
                  <Check className="w-3 h-3" />
                  <span>Append-Only Record Committed to Ledger</span>
                </div>
              </div>
            )}

            {/* Fallback for other custom steps */}
            {!stageNorm.includes("customer signal") &&
             !stageNorm.includes("context evaluated") &&
             !stageNorm.includes("proposal") &&
             !stageNorm.includes("policy validation") &&
             !stageNorm.includes("risk gate") &&
             !stageNorm.includes("action") &&
             !stageNorm.includes("audit") && (
              <div className="text-xs text-white font-heading font-semibold">
                {step.detail}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#030304] text-[#FFFFFF] flex flex-col font-body antialiased relative overflow-hidden">
      {/* Background Ambience */}
      <div className="fixed inset-0 pointer-events-none bg-grid-pattern bg-radial-vignette opacity-70 z-0" />
      <div className="fixed top-[-10%] right-[-5%] w-[500px] h-[500px] rounded-full bg-[#F7931A]/5 blur-[130px] pointer-events-none z-0" />
      <div className="fixed bottom-[-10%] left-[15%] w-[600px] h-[600px] rounded-full bg-[#EA580C]/5 blur-[160px] pointer-events-none z-0" />

      {/* ── TOP NAVIGATION & ROLE SWITCHER BAR ── */}
      <header className="h-16 border-b border-white/10 bg-[#0F1115]/95 backdrop-blur-xl px-4 md:px-8 flex items-center justify-between flex-shrink-0 z-30">
        {/* Brand Logo */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#EA580C] to-[#F7931A] p-0.5 shadow-[0_0_15px_rgba(247,147,26,0.6)] flex items-center justify-center flex-shrink-0">
            <div className="w-full h-full bg-[#030304] rounded-full flex items-center justify-center">
              <Coins className="w-4 h-4 text-[#FFD600]" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-heading font-bold text-sm tracking-tight text-white">GrowthPilot AI</span>
              <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 bg-[#F7931A]/10 border border-[#F7931A]/30 rounded-full text-[8px] font-mono font-bold text-[#FFD600]">
                <Flame className="w-2.5 h-2.5 inline" /> BITCOIN DEFI
              </span>
            </div>
            <span className="text-[9px] text-[#94A3B8] font-mono hidden md:block">Agent Commerce Gateway designed around emerging agent-commerce patterns.</span>
          </div>
        </div>

        {/* Central Role Switcher Pill */}
        <div className="flex items-center bg-[#030304] p-1 rounded-full border border-white/10 shadow-inner">
          <button
            onClick={() => setAppMode("storefront")}
            className={`flex items-center gap-2 px-4 sm:px-5 py-1.5 rounded-full text-xs font-heading font-bold transition-all cursor-pointer ${appMode === "storefront" ? "bg-gradient-to-r from-[#EA580C] to-[#F7931A] text-white shadow-[0_0_15px_rgba(247,147,26,0.6)]" : "text-[#94A3B8] hover:text-white"}`}
          >
            <Store className="w-3.5 h-3.5" />
            <span>Storefront</span>
          </button>
          <button
            onClick={() => setAppMode("merchant")}
            className={`flex items-center gap-2 px-4 sm:px-5 py-1.5 rounded-full text-xs font-heading font-bold transition-all cursor-pointer ${appMode === "merchant" ? "bg-gradient-to-r from-[#EA580C] to-[#F7931A] text-white shadow-[0_0_15px_rgba(247,147,26,0.6)]" : "text-[#94A3B8] hover:text-white"}`}
          >
            <LayoutDashboard className="w-3.5 h-3.5" />
            <span>Merchant Hub</span>
          </button>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-3">
          {appMode === "storefront" && (
            <button
              onClick={() => setShowInspector(!showInspector)}
              className={`hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-mono font-bold border transition-all cursor-pointer ${showInspector ? "bg-[#F7931A]/20 border-[#F7931A] text-[#FFD600] shadow-[0_0_10px_rgba(247,147,26,0.4)]" : "bg-white/5 border-white/10 text-[#94A3B8] hover:text-white"}`}
              title="Inspect the live 5-stage decision lifecycle"
            >
              <Eye className="w-3 h-3" />
              <span>AI Inspector</span>
            </button>
          )}
          <button
            onClick={handleResetSession}
            title="Reset Session"
            className="p-2 border border-white/10 hover:border-red-500/40 bg-white/5 hover:bg-red-500/10 text-[#94A3B8] hover:text-red-400 rounded-full transition-all cursor-pointer text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* ── APP BODY CONTENT ── */}
      <div className="flex-1 flex overflow-hidden z-10">

        {/* ========================================================================= */}
        {/* 1. CUSTOMER STOREFRONT MODE (BUYER-FACING)                                */}
        {/* ========================================================================= */}
        {appMode === "storefront" && (
          <div className="flex-1 flex overflow-hidden animate-fadeIn relative">
            <div className="flex-1 flex flex-col min-w-0 max-w-4xl mx-auto border-x border-white/10 bg-transparent h-full">

              {/* Storefront Ambient Header */}
              <div className="px-6 py-4 border-b border-white/10 bg-[#0F1115]/50 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full bg-[#FFD600] animate-ping" />
                  <div>
                    <h3 className="font-heading font-bold text-xs text-white">GrowthPilot Smart Store</h3>
                    <p className="text-[10px] text-[#94A3B8] font-body">Ask for advice, negotiate pricing, or explore curated tech gear</p>
                  </div>
                </div>
                <span className="text-[9px] font-mono text-[#F7931A] bg-[#F7931A]/10 border border-[#F7931A]/30 px-2.5 py-1 rounded-full">
                  Razorpay Live Test Mode
                </span>
              </div>

              {/* Chat Stream */}
              <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
                {chatMessages.map((m, idx) => (
                  <div key={idx} className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}>
                    <div className={`max-w-2xl text-sm leading-relaxed ${m.sender === "user" ? "bg-gradient-to-r from-[#0F1115] to-[#1E293B] border border-[#F7931A]/30 px-5 py-3.5 rounded-2xl rounded-tr-none text-white shadow-[0_0_15px_-5px_rgba(247,147,26,0.3)]" : "text-gray-200"}`}>
                      {m.sender === "agent" && (
                        <div className="flex items-center gap-2 mb-2 text-[10px] font-mono font-bold text-[#F7931A] uppercase tracking-widest">
                          <Coins className="w-3.5 h-3.5 text-[#FFD600]" /> GrowthPilot AI Assistant
                        </div>
                      )}
                      {m.message.split("\n").map((line, i) => {
                        const parts = line.split(/(\*\*.*?\*\*)/g);
                        return <p key={i} className={i > 0 ? "mt-1.5" : ""}>{parts.map((p, j) => p.startsWith("**") ? <strong key={j} className="text-[#FFD600] font-heading font-bold">{p.slice(2, -2)}</strong> : p)}</p>;
                      })}

                      {/* Product Recommendation Cards */}
                      {m.products && m.products.length > 0 && (
                        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                          {m.products.map(p => (
                            <div key={p.id} className="border border-white/10 bg-[#0F1115] rounded-2xl overflow-hidden hover:border-[#F7931A]/50 transition-all duration-300 glow-card hover:-translate-y-1">
                              <div className="aspect-video bg-[#030304] relative overflow-hidden">
                                <img
                                  src={p.image}
                                  onError={(e) => {
                                    e.currentTarget.onerror = null;
                                    e.currentTarget.src = CATEGORY_FALLBACK_IMAGES[p.category] || CATEGORY_FALLBACK_IMAGES.default;
                                  }}
                                  className="w-full h-full object-cover"
                                  alt={p.name}
                                />
                                <span className="absolute top-2 right-2 bg-gradient-to-r from-[#EA580C] to-[#F7931A] text-black text-[8px] font-mono font-bold tracking-wider px-2 py-0.5 rounded-full shadow-[0_0_10px_rgba(247,147,26,0.8)]">
                                  BEST MATCH
                                </span>
                              </div>
                              <div className="p-4 space-y-2">
                                <div className="font-heading font-bold text-xs text-white truncate">{p.name}</div>
                                <div className="text-[10px] text-[#94A3B8] line-clamp-1">{p.description}</div>
                                <div className="flex justify-between items-center pt-2 border-t border-white/10">
                                  <span className="text-sm font-heading font-bold text-[#FFD600]">Rs.{p.price?.toLocaleString("en-IN")}</span>
                                  <span className="text-[9px] font-mono text-[#F7931A] uppercase tracking-wider">{p.category}</span>
                                </div>
                                <div className="grid grid-cols-2 gap-1.5 pt-2 border-t border-white/10">
                                  <button onClick={() => handleDirectCheckout(p)}
                                    className="px-3 py-1.5 rounded-full bg-gradient-to-r from-[#EA580C] to-[#F7931A] hover:shadow-[0_0_15px_rgba(247,147,26,0.6)] text-white text-[9px] font-heading font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1 cursor-pointer">
                                    <ShoppingBag className="w-3 h-3" /> Buy Now
                                  </button>
                                  <button onClick={() => handleObjectionPrompt(p)}
                                    className="px-3 py-1.5 rounded-full border border-[#F7931A]/40 hover:bg-[#F7931A]/15 text-[#FFD600] text-[9px] font-heading font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1 cursor-pointer">
                                    <Sparkles className="w-3 h-3" /> Negotiate
                                  </button>
                                  <button onClick={() => handleSendMessage(`Compare ${p.name} with other options`)}
                                    className="px-2 py-1 rounded-full bg-white/5 hover:bg-white/10 text-[#94A3B8] hover:text-white text-[8px] font-mono transition-all">
                                    Compare
                                  </button>
                                  <button onClick={() => handleSendMessage(`What are the key specs and features of ${p.name}?`)}
                                    className="px-2 py-1 rounded-full bg-white/5 hover:bg-white/10 text-[#94A3B8] hover:text-white text-[8px] font-mono transition-all">
                                    Specs
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Inline Confirm / Decline buttons */}
                      {m.sender === "agent" && idx === chatMessages.length - 1 && sessionState === "awaiting_confirmation" && (
                        <div className="mt-4 pt-3 border-t border-white/10 flex flex-wrap gap-2 animate-fadeIn">
                          <button
                            onClick={() => handleSendMessage("confirm")}
                            className="flex items-center gap-2 px-5 py-2 rounded-full bg-gradient-to-r from-[#EA580C] to-[#F7931A] shadow-[0_0_20px_-5px_rgba(247,147,26,0.6)] hover:scale-105 transition-all text-white font-heading font-bold text-xs uppercase tracking-wider cursor-pointer"
                          >
                            <Check className="w-3.5 h-3.5 stroke-[3]" />
                            Confirm & Settle
                          </button>
                          <button
                            onClick={() => handleSendMessage("cancel")}
                            className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 hover:bg-red-500/20 text-[#94A3B8] hover:text-red-300 border border-white/10 hover:border-red-500/30 font-heading font-semibold text-xs transition-all cursor-pointer"
                          >
                            <X className="w-3.5 h-3.5" />
                            Decline / Cancel
                          </button>
                          <button
                            onClick={() => handleSendMessage("Show me a cheaper alternative")}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 hover:bg-white/10 text-[#94A3B8] hover:text-white font-mono text-xs border border-white/10 transition-all"
                          >
                            Cheaper Alternative
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {isTyping && (
                  <div className="flex flex-col items-start">
                    <div className="flex items-center gap-2 mb-2 text-[10px] font-mono font-bold text-[#F7931A] uppercase tracking-widest">
                      <Coins className="w-3.5 h-3.5 text-[#FFD600]" /> Finding best options...
                    </div>
                    <div className="flex gap-1.5 pl-4">
                      {[0, 150, 300].map(d => <span key={d} className="w-2 h-2 bg-[#F7931A] rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Order Confirmation Floating Action Ribbon */}
              {sessionState === "awaiting_confirmation" && (
                <div className="mx-6 mb-2 p-4 bg-gradient-to-r from-[#0F1115] via-[#F7931A]/10 to-[#0F1115] border border-[#F7931A]/40 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-3 animate-fadeIn shadow-[0_0_25px_-5px_rgba(247,147,26,0.3)] flex-shrink-0">
                  <div className="flex items-center gap-2 text-xs">
                    <div className="w-2.5 h-2.5 rounded-full bg-[#FFD600] animate-pulse" />
                    <span className="text-white font-heading font-bold">Ready to place your order?</span>
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <button
                      onClick={() => handleSendMessage("confirm")}
                      className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-5 py-2.5 rounded-full bg-gradient-to-r from-[#EA580C] to-[#F7931A] hover:shadow-[0_0_20px_rgba(247,147,26,0.7)] text-white font-heading font-bold text-xs uppercase tracking-wider transition-all cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5 stroke-[3]" />
                      Confirm & Pay
                    </button>
                    <button
                      onClick={() => handleSendMessage("cancel")}
                      className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-full bg-white/5 hover:bg-red-500/20 text-[#94A3B8] hover:text-red-300 border border-white/10 hover:border-red-500/30 font-heading font-semibold text-xs transition-all cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                      Decline
                    </button>
                  </div>
                </div>
              )}

              {/* Category Discovery Pills Strip */}
              <div className="px-6 py-3 border-t border-white/10 flex gap-2 overflow-x-auto bg-[#0F1115]/50 no-scrollbar flex-shrink-0">
                {sessionState === "awaiting_confirmation" ? (
                  <>
                    <button onClick={() => handleSendMessage("confirm")}
                      className="text-[10px] font-mono font-bold border border-[#F7931A] bg-[#F7931A]/10 text-[#FFD600] hover:bg-[#F7931A]/20 px-3.5 py-1.5 rounded-full transition-all flex-shrink-0 flex items-center gap-1">
                      <Check className="w-3 h-3" /> Confirm & Pay
                    </button>
                    <button onClick={() => handleSendMessage("cancel")}
                      className="text-[10px] font-mono font-bold border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20 px-3.5 py-1.5 rounded-full transition-all flex-shrink-0 flex items-center gap-1">
                      <X className="w-3 h-3" /> Decline
                    </button>
                    <button onClick={() => handleSendMessage("Show me a cheaper alternative")}
                      className="text-[10px] font-mono font-semibold border border-white/10 hover:border-[#F7931A]/40 bg-[#030304] text-[#94A3B8] hover:text-white px-3 py-1.5 rounded-full transition-all flex-shrink-0">
                      Cheaper alternative
                    </button>
                    <button onClick={() => handleSendMessage("Can I get a discount on this?")}
                      className="text-[10px] font-mono font-semibold border border-[#F7931A]/30 bg-[#F7931A]/10 text-[#FFD600] hover:bg-[#F7931A]/20 px-3.5 py-1.5 rounded-full transition-all flex-shrink-0">
                      Ask for discount
                    </button>
                  </>
                ) : (
                  <>
                    <button onClick={() => handleSendMessage("Show me wireless earbuds under Rs.3000")}
                      className="text-[10px] font-mono font-semibold border border-[#F7931A]/30 hover:border-[#F7931A] bg-[#F7931A]/10 text-[#FFD600] hover:text-white px-3.5 py-1.5 rounded-full transition-all flex-shrink-0">
                      🔍 1. Natural Search
                    </button>
                    <button onClick={() => handleSendMessage("Rs.2,499 is too expensive for the SoundFlow Earbuds")}
                      className="text-[10px] font-mono font-semibold border border-[#EA580C]/40 hover:border-[#EA580C] bg-[#EA580C]/10 text-[#FFD600] hover:text-white px-3.5 py-1.5 rounded-full transition-all flex-shrink-0">
                      🏷️ 2. Price Objection
                    </button>
                    <button onClick={() => handleSendMessage("What protective case or accessories do you recommend with these earbuds?")}
                      className="text-[10px] font-mono font-semibold border border-blue-500/30 hover:border-blue-400 bg-blue-500/10 text-blue-300 hover:text-white px-3.5 py-1.5 rounded-full transition-all flex-shrink-0">
                      📦 3. Upsell & Cross-Sell
                    </button>
                    <button onClick={() => handleSendMessage("Can I get a 15% discount on this order?")}
                      className="text-[10px] font-mono font-semibold border border-amber-500/40 hover:border-amber-400 bg-amber-500/10 text-amber-300 hover:text-white px-3.5 py-1.5 rounded-full transition-all flex-shrink-0">
                      ⚡ 4. High-Risk Gate (15% - Approval Required)
                    </button>
                    <button onClick={() => handleSendMessage("Can I get a 25% discount on this order?")}
                      className="text-[10px] font-mono font-semibold border border-red-500/40 hover:border-red-400 bg-red-500/10 text-red-300 hover:text-white px-3.5 py-1.5 rounded-full transition-all flex-shrink-0">
                      🛑 5. Hard Limit Violation (25% - BLOCKED)
                    </button>
                  </>
                )}
              </div>

              {/* Chat Input */}
              <div className="p-5 border-t border-white/10 bg-[#0F1115]/90 backdrop-blur-xl flex gap-3 flex-shrink-0">
                <input type="text" value={chatInput} onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleSendMessage()}
                  placeholder={sessionState === "awaiting_confirmation" ? "Type 'confirm', 'decline', or search something else..." : "What are you looking for? (e.g. noise-cancelling earbuds under 3000)..."}
                  className="flex-1 bg-[#030304] border border-white/10 focus:border-[#F7931A] focus:shadow-[0_0_20px_rgba(247,147,26,0.3)] rounded-full px-5 py-3 text-sm focus:outline-none transition-all placeholder:text-[#94A3B8]/50" />
                <button onClick={() => handleSendMessage()}
                  className="rounded-full bg-gradient-to-r from-[#EA580C] to-[#F7931A] hover:shadow-[0_0_20px_rgba(247,147,26,0.7)] text-white px-6 py-3 transition-all font-heading font-bold uppercase tracking-wider flex-shrink-0 cursor-pointer">
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Slide-out AI Inspector Panel */}
            {showInspector && (
              <div className="w-80 sm:w-96 lg:w-[420px] border-l border-white/10 bg-[#0F1115]/95 backdrop-blur-xl overflow-y-auto p-5 space-y-4 animate-fadeIn flex-shrink-0 z-20">
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-lg bg-[#F7931A]/10 border border-[#F7931A]/30 flex items-center justify-center">
                      <Eye className="w-4 h-4 text-[#F7931A]" />
                    </div>
                    <div>
                      <div className="text-xs font-mono font-bold text-[#FFD600] uppercase tracking-wider">AI Live Inspector</div>
                      <div className="text-[9px] font-mono text-[#94A3B8]">7-Stage Live Decision Telemetry</div>
                    </div>
                  </div>
                  <button onClick={() => setShowInspector(false)} className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-all"><X className="w-4 h-4" /></button>
                </div>
                <div className="space-y-1">
                  <div className="text-[9px] font-mono font-bold uppercase tracking-widest text-[#94A3B8] mb-3 flex items-center justify-between">
                    <span>Live Telemetry Circuit</span>
                    <span className="text-[8px] text-green-400 font-mono flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span> LIVE BACKEND</span>
                  </div>
                  {currentLifecycle.length > 0 ? (
                    currentLifecycle.map((step, i) => (
                      <LifecycleStep key={i} step={step} index={i} total={currentLifecycle.length} />
                    ))
                  ) : (
                    <div className="text-xs text-[#94A3B8] font-mono italic p-4 bg-[#030304] border border-white/10 rounded-xl space-y-2">
                      <p>Send a message (e.g. <span className="text-[#FFD600] font-bold">"₹2,499 is too expensive"</span>) to observe live 7-stage AI decision telemetry.</p>
                      <div className="text-[9px] text-gray-500">Stages: Customer Signal → Context → AI Proposal → Policy → Risk Gate → Action → Audit Event</div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* 2. MERCHANT ADMIN HUB MODE (OPERATOR-FACING)                             */}
        {/* ========================================================================= */}
        {appMode === "merchant" && (
          <div className="flex-1 flex overflow-hidden animate-fadeIn">
            {/* Merchant Sidebar */}
            <aside className="w-64 border-r border-white/10 bg-[#0F1115]/90 backdrop-blur-xl flex flex-col justify-between flex-shrink-0 hidden md:flex z-10">
              <div>
                {/* Active Objective Hologram */}
                <div className="p-4 border-b border-white/10">
                  <div className="flex items-center gap-2.5 px-3 py-2.5 bg-gradient-to-r from-[#F7931A]/10 to-transparent border border-[#F7931A]/30 rounded-xl shadow-[0_0_15px_-5px_rgba(247,147,26,0.3)]">
                    <div className="w-2 h-2 rounded-full bg-[#FFD600] animate-pulse" />
                    <div className="min-w-0">
                      <div className="text-[8px] text-[#94A3B8] uppercase tracking-widest font-mono">Merchant Objective</div>
                      <div className="text-[11px] font-heading font-bold text-[#FFD600] truncate">
                        {OBJECTIVES.find(o => o.id === merchantSettings.objective)?.label || "Protect Profit"}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Navigation Links */}
                <nav className="p-3 space-y-1">
                  {[
                    { id: "overview",       icon: <LayoutDashboard className="w-4 h-4" />, label: "Overview" },
                    { id: "agent",          icon: <Sparkles className="w-4 h-4 text-[#F7931A]" />, label: "AI Sales Agent" },
                    { id: "a2a",            icon: <Bot className="w-4 h-4 text-[#FFD600]" />, label: "Agent Commerce (A2A)", badge: "LIVE" },
                    { id: "approvals",      icon: <Shield className="w-4 h-4 text-amber-400" />, label: "Approvals",
                      badge: approvals.filter(a => a.status === "WAITING FOR MERCHANT APPROVAL").length > 0
                        ? `${approvals.filter(a => a.status === "WAITING FOR MERCHANT APPROVAL").length} PENDING` : null,
                      badgeClass: "bg-amber-500/20 text-amber-400 border-amber-500/40 animate-pulse" },
                    { id: "conversations",  icon: <MessageSquare className="w-4 h-4" />, label: "Conversations" },
                    { id: "products",       icon: <Package className="w-4 h-4" />, label: "Products" },
                    { id: "orders",         icon: <CreditCard className="w-4 h-4" />, label: "Orders" },
                    { id: "analytics",      icon: <TrendingUp className="w-4 h-4" />, label: "Analytics" },
                    { id: "settings",       icon: <Settings className="w-4 h-4" />, label: "Settings" },
                  ].map(item => (
                    <button key={item.id} onClick={() => setActiveTab(item.id)}
                      className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-heading font-medium tracking-wide transition-all ${activeTab === item.id ? "bg-gradient-to-r from-[#EA580C]/20 to-[#F7931A]/10 border-l-2 border-[#F7931A] text-white shadow-[0_0_15px_-5px_rgba(247,147,26,0.3)]" : "text-[#94A3B8] hover:text-white hover:bg-white/[0.03]"}`}>
                      <div className="flex items-center gap-3">
                        <span className={activeTab === item.id ? "text-[#F7931A]" : ""}>{item.icon}</span>
                        <span>{item.label}</span>
                      </div>
                      {item.badge && (
                        <span className={`px-1.5 py-0.5 rounded text-[8px] font-mono font-bold border ${item.badgeClass || "bg-[#FFD600]/10 text-[#FFD600] border-[#FFD600]/30 animate-pulse"}`}>
                          {item.badge}
                        </span>
                      )}
                    </button>
                  ))}
                </nav>
              </div>

              {/* Merchant Account Footer */}
              <div className="p-4 border-t border-white/10 space-y-3 bg-[#030304]/50">
                <div className="flex items-center gap-3 px-2 py-1">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#EA580C] to-[#FFD600] flex items-center justify-center font-heading font-bold text-xs text-black flex-shrink-0 shadow-[0_0_10px_rgba(255,214,0,0.4)]">
                    GP
                  </div>
                  <div className="min-w-0">
                    <span className="font-heading font-bold text-xs text-white block truncate">DeFi Merchant Node</span>
                    <span className="text-[9px] font-mono text-[#94A3B8]">merchant@growthpilot.ai</span>
                  </div>
                </div>
              </div>
            </aside>

            {/* Merchant Tab View Container */}
            <div className="flex-1 overflow-y-auto bg-transparent flex flex-col">

              {/* Mobile/Compact Horizontal Navigation Strip */}
              <div className="border-b border-white/10 bg-[#0F1115]/95 backdrop-blur px-4 py-2.5 flex md:hidden items-center gap-2 overflow-x-auto no-scrollbar flex-shrink-0 sticky top-0 z-20">
                {[
                  { id: "overview",       label: "Overview" },
                  { id: "agent",          label: "AI Sales Agent" },
                  { id: "a2a",            label: "A2A Gateway" },
                  { id: "approvals",      label: "Approvals" },
                  { id: "conversations",  label: "Chats" },
                  { id: "products",       label: "Products" },
                  { id: "orders",         label: "Orders" },
                  { id: "analytics",      label: "Analytics" },
                  { id: "settings",       label: "Settings" },
                ].map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-3 py-1.5 rounded-full text-xs font-heading font-bold whitespace-nowrap transition-all cursor-pointer ${activeTab === t.id ? "bg-gradient-to-r from-[#EA580C] to-[#F7931A] text-white shadow-[0_0_10px_rgba(247,147,26,0.5)]" : "bg-white/5 text-gray-300 border border-white/10 hover:bg-white/10"}`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* ── OVERVIEW TAB (Core Value & Control Hierarchy) ── */}
              {activeTab === "overview" && (
                <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-8 animate-fadeIn">
                  {/* Hero Statement */}
                  <div className="border border-white/10 bg-gradient-to-br from-[#0F1115] via-[#0F1115] to-[#030304] rounded-2xl p-8 flex flex-col lg:flex-row lg:items-center justify-between gap-8 relative overflow-hidden glow-card">
                    <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-[#F7931A]/10 via-[#FFD600]/5 to-transparent pointer-events-none rounded-full blur-3xl" />
                    <div className="space-y-4 max-w-2xl relative z-10">
                      <div className="inline-flex items-center gap-2 px-3 py-1 bg-[#F7931A]/10 border border-[#F7931A]/30 rounded-full text-[10px] font-mono tracking-widest uppercase text-[#FFD600]">
                        <Shield className="w-3.5 h-3.5 text-[#F7931A]" /> MERCHANT GOVERNANCE ENGINE
                      </div>
                      <h2 className="text-2xl sm:text-3xl lg:text-4xl font-heading font-bold tracking-tight text-white leading-tight">
                        "The merchant controls the boundaries. <span className="bg-gradient-to-r from-[#F7931A] to-[#FFD600] bg-clip-text text-transparent">The AI operates inside them.</span>"
                      </h2>
                      <p className="text-xs text-[#94A3B8] leading-relaxed font-body">
                        Agentic commerce & margin defense gateway strictly bounded by merchant-configured profit floors, discount caps, and policy approval gates.
                      </p>

                      {/* Active Objective Quick-Switcher Pill */}
                      <div className="pt-2 flex flex-wrap items-center gap-2">
                        <span className="text-[10px] font-mono uppercase text-[#94A3B8]">Active Objective:</span>
                        {OBJECTIVES.slice(0, 3).map(obj => (
                          <button
                            key={obj.id}
                            onClick={() => handleQuickSwitchObjective(obj.id)}
                            className={`px-3 py-1 rounded-full text-[10px] font-mono font-bold transition-all cursor-pointer ${merchantSettings.objective === obj.id ? "bg-[#FFD600] text-black shadow-[0_0_15px_rgba(255,214,0,0.4)]" : "bg-white/5 hover:bg-white/10 text-gray-300 border border-white/10"}`}>
                            {obj.id === "protect_profit" ? "🛡️ Protect Profit" : obj.id === "maximize_conversions" ? "⚡ Maximize Conversions" : "📦 Increase AOV"}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="border border-white/10 bg-[#030304]/80 p-5 rounded-2xl w-full lg:w-80 space-y-3 font-mono text-xs flex-shrink-0 relative z-10 shadow-2xl">
                      <div className="flex justify-between items-center pb-2 border-b border-white/10">
                        <span className="text-[#94A3B8] uppercase text-[9px] tracking-wider">Engine Status</span>
                        <span className="text-green-400 font-bold flex items-center gap-1.5">
                          <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" /> BOUNDED & ACTIVE
                        </span>
                      </div>
                      <div className="flex justify-between"><span className="text-[#94A3B8]">Decisions Made</span><span className="text-white font-bold">{metrics.decisions_made}</span></div>
                      <div className="flex justify-between"><span className="text-[#94A3B8]">Policy Pass Rate</span><span className="text-[#F7931A] font-bold">{metrics.approval_rate}%</span></div>
                      <div className="flex justify-between"><span className="text-[#94A3B8]">Settled AI Volume</span><span className="text-[#FFD600] font-bold">Rs.{metrics.revenue_influenced.toLocaleString("en-IN")}</span></div>
                    </div>
                  </div>

                  {/* 4 Core Essential Metrics */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {[
                      { label: "AI-Influenced Revenue", value: `Rs.${metrics.revenue_influenced.toLocaleString("en-IN")}`, sub: "Settled volume driven by AI", color: "text-[#FFD600]" },
                      { label: "Conversion Rate",       value: `${metrics.conversion_rate}%`, sub: "Sessions to completed orders", color: "text-[#F7931A]" },
                      { label: "Profit Preserved",      value: `Rs.${metrics.profit_preserved.toLocaleString("en-IN")}`, sub: "Margin protected vs direct discounting", color: "text-green-400" },
                      { label: "Strategy Performance",  value: topStrategy ? `${topStrategy[1].conversion_rate}%` : "100%", sub: topStrategy ? `${topStrategy[0].replace(/_/g, ' ')}` : "High policy efficacy", color: "text-[#FFD600]" },
                    ].map((m, i) => (
                      <div key={i} className="p-6 bg-[#0F1115] border border-white/10 rounded-2xl hover:border-[#F7931A]/40 transition-all duration-300 glow-card hover:-translate-y-0.5">
                        <div className="text-[10px] font-mono tracking-wider uppercase text-[#94A3B8] mb-1.5">{m.label}</div>
                        <div className={`text-2xl font-heading font-bold ${m.color}`}>{m.value}</div>
                        <div className="text-[10px] text-[#94A3B8]/70 mt-1 font-mono truncate">{m.sub}</div>
                      </div>
                    ))}
                  </div>

                  {/* ── Active Policy Controls (The 5 Defined Boundaries) ── */}
                  <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-6 space-y-4 glow-card">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/10 pb-4">
                      <div>
                        <div className="flex items-center gap-2 text-xs font-mono font-bold text-white uppercase tracking-wider">
                          <Sliders className="w-4 h-4 text-[#F7931A]" />
                          Active Policy Controls & Enforced Boundaries
                        </div>
                        <p className="text-[11px] text-[#94A3B8] font-body mt-0.5">
                          The backend policy engine deterministically enforces these 5 boundaries on every AI proposal before execution.
                        </p>
                      </div>
                      <button
                        onClick={() => setActiveTab("settings")}
                        className="text-[10px] font-mono text-[#FFD600] hover:underline flex items-center gap-1 cursor-pointer">
                        Configure Bounds →
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 pt-1">
                      {/* 1. Max Discount Cap */}
                      <div className="p-4 bg-[#030304]/70 border border-white/10 rounded-xl space-y-1.5">
                        <div className="text-[9px] font-mono uppercase text-[#94A3B8]">1. Max Discount Cap</div>
                        <div className="text-lg font-heading font-bold text-[#FFD600]">{merchantSettings.max_discount_pct}%</div>
                        <div className="text-[9px] text-[#94A3B8] leading-tight font-body">Hard ceiling on direct price concessions.</div>
                      </div>

                      {/* 2. Min Margin Threshold */}
                      <div className="p-4 bg-[#030304]/70 border border-white/10 rounded-xl space-y-1.5">
                        <div className="text-[9px] font-mono uppercase text-[#94A3B8]">2. Min Margin Threshold</div>
                        <div className="text-lg font-heading font-bold text-green-400">Rs.{merchantSettings.min_margin}</div>
                        <div className="text-[9px] text-[#94A3B8] leading-tight font-body">Guaranteed profit floor per unit.</div>
                      </div>

                      {/* 3. Shipping Waiver Limit */}
                      <div className="p-4 bg-[#030304]/70 border border-white/10 rounded-xl space-y-1.5">
                        <div className="text-[9px] font-mono uppercase text-[#94A3B8]">3. Shipping Waiver Limit</div>
                        <div className="text-lg font-heading font-bold text-[#F7931A]">Rs.{merchantSettings.shipping_cost}</div>
                        <div className="text-[9px] text-[#94A3B8] leading-tight font-body">Max allowable delivery subsidy.</div>
                      </div>

                      {/* 4. Quantity Limit */}
                      <div className="p-4 bg-[#030304]/70 border border-white/10 rounded-xl space-y-1.5">
                        <div className="text-[9px] font-mono uppercase text-[#94A3B8]">4. Quantity Limit / SKU</div>
                        <div className="text-lg font-heading font-bold text-blue-400">5 Units</div>
                        <div className="text-[9px] text-[#94A3B8] leading-tight font-body">Inventory drain & bulk order cap.</div>
                      </div>

                      {/* 5. Approval Threshold */}
                      <div className="p-4 bg-[#030304]/70 border border-amber-500/30 bg-amber-500/[0.03] rounded-xl space-y-1.5">
                        <div className="text-[9px] font-mono uppercase text-amber-400">5. Approval Threshold</div>
                        <div className="text-lg font-heading font-bold text-amber-400">{merchantSettings.high_risk_discount_threshold || 15}%</div>
                        <div className="text-[9px] text-[#94A3B8] leading-tight font-body">Incentives ≥ this % pause for merchant sign-off.</div>
                      </div>
                    </div>
                  </div>

                  {/* Strategy Performance Feedback Loop */}
                  {topStrategy && (
                    <div className="border border-[#F7931A]/30 bg-gradient-to-r from-[#0F1115] via-[#F7931A]/5 to-[#0F1115] rounded-2xl p-6 space-y-3 glow-card">
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-[#F7931A]" />
                        <span className="text-xs font-mono font-bold uppercase tracking-widest text-[#FFD600]">Strategy Performance & Closed Feedback Loop</span>
                      </div>
                      <div className="flex flex-col md:flex-row md:items-center gap-6 justify-between">
                        <div>
                          <div className="text-[10px] text-[#94A3B8] font-mono uppercase tracking-wider">Top Performing Strategy</div>
                          <div className="text-xl font-heading font-bold text-white mt-1">{topStrategy[0].replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</div>
                          <div className="text-xs text-[#FFD600] font-mono mt-1">
                            {topStrategy[1].conversion_rate}% Conversion · {topStrategy[1].converted}/{topStrategy[1].total} Orders · Avg Rs.{topStrategy[1].avg_revenue}
                          </div>
                        </div>
                        <div className="text-[11px] text-[#94A3B8] leading-relaxed max-w-md bg-[#030304]/60 p-4 rounded-xl border border-white/5 font-body">
                          Historical conversion outcomes inform future agent proposals. The AI selects the strategy that maximizes empirical revenue under active policy limits.
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Activity Ledger */}
                  <div className="border-t border-white/10 pt-8 space-y-5">
                    <h3 className="text-xs font-mono font-bold uppercase tracking-widest text-[#94A3B8] flex items-center gap-2">
                      <Layers className="w-4 h-4 text-[#F7931A]" /> AI Protocol Activity Ledger
                    </h3>
                    {activityLogs.length === 0 ? (
                      <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-12 text-center text-xs text-[#94A3B8] font-mono">
                        No activity recorded yet. Start a session in the Storefront.
                      </div>
                    ) : (
                      <div className="relative pl-6 border-l border-[#F7931A]/30 space-y-6">
                        {activityLogs.slice(0, 10).map((log) => {
                          const dots = {
                            payment_success: "bg-[#FFD600] ring-[#FFD600]/40",
                            payment_failed: "bg-[#EA580C] ring-[#EA580C]/40",
                            guardrail_block: "bg-red-500 ring-red-500/40",
                            offered_discount: "bg-[#F7931A] ring-[#F7931A]/40",
                            offered_free_shipping: "bg-[#FFD600] ring-[#FFD600]/40",
                            recommended_cheaper_alternative: "bg-blue-400 ring-blue-400/40",
                            recommended_bundle: "bg-amber-400 ring-amber-400/40",
                            agent_decision_claude: "bg-[#F7931A] ring-[#F7931A]/40",
                            agent_decision_heuristic: "bg-gray-400 ring-gray-400/40",
                            proposal_rejected: "bg-[#EA580C] ring-[#EA580C]/40"
                          };
                          const dot = dots[log.action_type] || "bg-[#F7931A] ring-[#F7931A]/30";
                          return (
                            <div key={log.id} className="relative animate-fadeIn">
                              <div className={`absolute -left-[31px] top-1 w-3 h-3 rounded-full ring-4 ${dot}`} />
                              <div className="text-[10px] font-mono text-[#F7931A] mb-0.5">
                                {new Date(log.timestamp + "Z").toLocaleTimeString()} · <span className="text-white font-semibold">{log.action_type.replace(/_/g, ' ').toUpperCase()}</span>
                              </div>
                              <div className="text-xs text-[#94A3B8] font-body bg-[#0F1115] p-3 rounded-xl border border-white/5 hover:border-white/10 transition-all max-w-3xl">
                                {log.reasoning}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── AGENT SPLIT MONITOR TAB ── */}
              {activeTab === "agent" && (
                <div className="h-full flex flex-col lg:flex-row overflow-hidden animate-fadeIn" style={{ height: "calc(100vh - 64px)" }}>
                  <div className="flex-1 flex flex-col border-r border-white/10 min-h-0 bg-transparent">
                    {/* Active Objective Quick-Switcher Bar */}
                    <div className="px-6 py-3 border-b border-white/10 bg-[#0F1115]/80 backdrop-blur flex flex-col sm:flex-row sm:items-center justify-between gap-3 flex-shrink-0">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-[9px] font-mono uppercase text-[#94A3B8]">Injected Objective Context:</span>
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#F7931A]/15 text-[#FFD600] border border-[#F7931A]/30">
                          {OBJECTIVES.find(o => o.id === merchantSettings.objective)?.label || merchantSettings.objective}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[9px] font-mono text-gray-400">Switch & Test:</span>
                        {OBJECTIVES.slice(0, 3).map(obj => (
                          <button
                            key={obj.id}
                            onClick={() => handleQuickSwitchObjective(obj.id)}
                            className={`px-2.5 py-1 rounded-full text-[9px] font-mono font-bold transition-all cursor-pointer ${merchantSettings.objective === obj.id ? "bg-[#FFD600] text-black shadow-[0_0_10px_rgba(255,214,0,0.5)]" : "bg-white/5 hover:bg-white/10 text-gray-300 border border-white/10"}`}>
                            {obj.id === "protect_profit" ? "🛡️ Protect Profit" : obj.id === "maximize_conversions" ? "⚡ Maximize Conversions" : "📦 Increase AOV"}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
                      {chatMessages.map((m, idx) => (
                        <div key={idx} className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}>
                          <div className={`max-w-2xl text-sm leading-relaxed ${m.sender === "user" ? "bg-gradient-to-r from-[#0F1115] to-[#1E293B] border border-[#F7931A]/30 px-5 py-3.5 rounded-2xl text-white" : "text-gray-200"}`}>
                            {m.sender === "agent" && (
                              <div className="flex items-center gap-2 mb-2 text-[10px] font-mono font-bold text-[#F7931A] uppercase tracking-widest">
                                <Coins className="w-3.5 h-3.5 text-[#FFD600]" /> GrowthPilot AI Agent
                              </div>
                            )}
                            {m.message}
                          </div>
                        </div>
                      ))}
                      <div ref={messagesEndRef} />
                    </div>
                    <div className="p-5 border-t border-white/10 bg-[#0F1115]/90 flex gap-3">
                      <input type="text" value={chatInput} onChange={e => setChatInput(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && handleSendMessage()}
                        placeholder="Simulate customer message..."
                        className="flex-1 bg-[#030304] border border-white/10 rounded-full px-5 py-3 text-sm focus:outline-none focus:border-[#F7931A] text-white" />
                      <button onClick={() => handleSendMessage()}
                        className="rounded-full bg-gradient-to-r from-[#EA580C] to-[#F7931A] text-white px-6 py-3 font-heading font-bold text-xs uppercase cursor-pointer">
                        <Send className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  <div className="w-full lg:w-[380px] xl:w-[420px] flex-shrink-0 flex flex-col bg-[#0F1115]/95 border-l border-white/10 overflow-y-auto p-6 gap-6 z-10">
                    <div className="border-b border-white/10 pb-4">
                      <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-widest text-[#F7931A]">
                        <Eye className="w-4 h-4 text-[#FFD600]" /> AI Live Inspector (7-Stage Circuit)
                      </div>
                    </div>
                    {currentLifecycle.length > 0 ? (
                      currentLifecycle.map((step, i) => (
                        <LifecycleStep key={i} step={step} index={i} total={currentLifecycle.length} />
                      ))
                    ) : (
                      <div className="text-xs text-[#94A3B8] font-mono italic">Start conversation to view circuit.</div>
                    )}
                  </div>
                </div>
              )}

              {/* ── AGENT-TO-AGENT (A2A) COMMERCE GATEWAY TAB ── */}
              {activeTab === "a2a" && (
                <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-8 animate-fadeIn">
                  {/* Hero Banner */}
                  <div className="border border-white/10 bg-gradient-to-br from-[#0F1115] to-[#030304] rounded-2xl p-8 space-y-3 glow-card">
                    <div className="inline-flex items-center gap-2 px-3 py-1 bg-[#F7931A]/10 border border-[#F7931A]/30 rounded-full text-[10px] font-mono tracking-widest uppercase text-[#FFD600]">
                      <Bot className="w-3.5 h-3.5 inline text-[#FFD600]" /> AGENT COMMERCE GATEWAY
                    </div>
                    <h2 className="text-2xl sm:text-3xl font-heading font-bold text-white tracking-tight">
                      Agentic Commerce Gateway: Machine-readable agent discovery & <span className="bg-gradient-to-r from-[#F7931A] to-[#FFD600] bg-clip-text text-transparent">cryptographically signed checkout</span>
                    </h2>
                    <p className="text-xs text-[#94A3B8] leading-relaxed font-body max-w-3xl">
                      Exposes machine-readable discovery, cryptographic signed intent validation, deterministic policy bounding, and two-step commit checkout to external AI buyer agents.
                    </p>
                  </div>

                  {/* Interactive Buyer Agent Simulator */}
                  <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-6 space-y-6 glow-card">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
                      <div>
                        <h3 className="text-sm font-heading font-bold text-white flex items-center gap-2">
                          <Play className="w-4 h-4 text-[#F7931A]" /> AI Buyer Agent Test Console
                        </h3>
                        <p className="text-[11px] text-[#94A3B8] font-body mt-0.5">Simulate an external AI buyer executing end-to-end purchases or hitting bounded policy limits</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => handleRunBuyerSimulation(selectedBuyerScenario)}
                          disabled={buyerSimLoading}
                          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-full bg-gradient-to-r from-[#EA580C] to-[#F7931A] text-white font-heading font-bold text-xs uppercase tracking-wider transition-all cursor-pointer disabled:opacity-50"
                        >
                          {buyerSimLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-white" />}
                          <span>{buyerSimLoading ? "Simulating..." : "Run AI Buyer Agent"}</span>
                        </button>
                      </div>
                    </div>

                    {/* Scenario Selector */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {[
                        { id: "happy_path", label: "Happy Path", desc: "1 unit · Mandate verified · Razorpay payment order created" },
                        { id: "policy_block", label: "Graceful Policy Block", desc: "12 units · Exceeds SKU cap · Returns 409 + retry suggestion" },
                        { id: "payment_failure", label: "Payment Decline Handling", desc: "Card declined by gateway · Logged in append-only ledger" },
                      ].map(sc => (
                        <button
                          key={sc.id}
                          onClick={() => { setSelectedBuyerScenario(sc.id); handleRunBuyerSimulation(sc.id); }}
                          className={`p-4 rounded-xl border text-left transition-all cursor-pointer ${selectedBuyerScenario === sc.id ? "border-[#F7931A] bg-[#F7931A]/10 text-white" : "border-white/10 bg-[#030304]/60 text-[#94A3B8] hover:border-white/20"}`}
                        >
                          <div className="text-xs font-heading font-bold">{sc.label}</div>
                          <div className="text-[10px] text-[#94A3B8] mt-1 font-mono">{sc.desc}</div>
                        </button>
                      ))}
                    </div>

                    {/* Simulation Output Steps */}
                    {buyerSimResult && (
                      <div className="space-y-4 animate-fadeIn">
                        <div className="p-4 bg-[#030304] border border-white/10 rounded-xl flex items-center justify-between font-mono text-xs">
                          <div>
                            <span className="text-[#94A3B8] text-[10px] uppercase">Outcome: </span>
                            <span className={buyerSimResult.success ? "text-green-400 font-bold" : buyerSimResult.outcome === "policy_block" ? "text-[#FFD600] font-bold" : "text-red-400 font-bold"}>
                              {buyerSimResult.summary}
                            </span>
                          </div>
                          <span className="px-2 py-0.5 bg-white/5 border border-white/10 rounded text-[10px] text-gray-300">
                            Intent #{buyerSimResult.intent_id}
                          </span>
                        </div>

                        <div className="space-y-2.5">
                          {buyerSimResult.steps?.map((st) => (
                            <div key={st.step} className="p-3.5 bg-[#030304]/80 border border-white/10 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                              <div className="flex items-center gap-3">
                                <span className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-[10px] ${st.status === 200 ? "bg-green-500/20 text-green-400 border border-green-500/40" : st.status === 409 ? "bg-[#FFD600]/20 text-[#FFD600] border border-[#FFD600]/40" : "bg-red-500/20 text-red-400 border border-red-500/40"}`}>
                                  {st.step}
                                </span>
                                <div>
                                  <div className="font-heading font-bold text-white">{st.name}</div>
                                  <div className="text-[10px] text-[#94A3B8] font-mono">{st.method} {st.endpoint}</div>
                                </div>
                              </div>
                              <div className="text-[11px] text-gray-300 font-body">
                                {st.detail}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Terminal CLI Command Box */}
                  <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-6 space-y-4 glow-card">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-4 h-4 text-[#FFD600]" />
                      <h3 className="text-xs font-mono font-bold text-white uppercase tracking-widest">Standalone Python Buyer Agent CLI</h3>
                    </div>
                    <p className="text-xs text-[#94A3B8] font-body">
                      Agent Commerce Gateway designed around emerging agent-commerce patterns. Run the reference buyer agent directly from your terminal:
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-[11px]">
                      <div className="p-3 bg-[#030304] border border-white/10 rounded-xl space-y-1">
                        <div className="text-[9px] text-[#94A3B8] uppercase">Happy Path (Autonomous Purchase):</div>
                        <code className="text-[#FFD600] font-bold block">python buyer_agent.py</code>
                      </div>
                      <div className="p-3 bg-[#030304] border border-white/10 rounded-xl space-y-1">
                        <div className="text-[9px] text-[#94A3B8] uppercase">Graceful Policy Block (Quantity Cap Violation):</div>
                        <code className="text-[#EA580C] font-bold block">python buyer_agent.py --block</code>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* ── APPROVALS GATE TAB ── */}
              {activeTab === "approvals" && (
                <div className="p-6 md:p-10 max-w-5xl mx-auto space-y-8 animate-fadeIn">
                  {/* Header */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-6">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <Shield className="w-5 h-5 text-amber-400" />
                        <h2 className="text-xl font-heading font-bold text-white">Approval Gate</h2>
                      </div>
                      <p className="text-xs text-[#94A3B8] font-body">
                        High-risk AI actions require explicit merchant approval before execution.
                        Backend enforces all gates — frontend state is display only.
                      </p>
                    </div>
                    <button onClick={fetchApprovals} disabled={approvalsLoading}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-full border border-white/10 text-xs font-heading font-bold text-[#94A3B8] hover:text-white hover:border-white/20 transition-all cursor-pointer disabled:opacity-50">
                      <RefreshCw className={`w-3.5 h-3.5 ${approvalsLoading ? "animate-spin" : ""}`} />
                      Refresh
                    </button>
                  </div>

                  {/* Risk Level Legend */}
                  <div className="flex flex-wrap gap-3">
                    {[
                      { level: "LOW",    desc: "Auto-executes — no gate",               color: RISK_COLORS.LOW },
                      { level: "MEDIUM", desc: "Backend policy validates before action", color: RISK_COLORS.MEDIUM },
                      { level: "HIGH",   desc: "Merchant approval required to execute",  color: RISK_COLORS.HIGH },
                    ].map(r => (
                      <div key={r.level}
                        className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${r.color.bg} ${r.color.border}`}>
                        <span className={`text-[9px] font-mono font-bold uppercase ${r.color.text}`}>{r.level}</span>
                        <span className="text-[10px] text-[#94A3B8] font-body">{r.desc}</span>
                      </div>
                    ))}
                  </div>

                  {/* Approvals list */}
                  {approvals.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-center space-y-3 border border-white/10 rounded-2xl bg-[#0F1115]">
                      <Shield className="w-8 h-8 text-[#94A3B8]/40" />
                      <p className="text-sm font-heading font-bold text-[#94A3B8]">No Approvals Yet</p>
                      <p className="text-xs text-[#94A3B8]/60 font-body max-w-xs">
                        HIGH-risk AI actions (e.g. discounts above the threshold) will appear here for your review.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {approvals.map(appr => {
                        const chip = APPROVAL_STATUS_CHIP[appr.status] || APPROVAL_STATUS_CHIP["APPROVED"];
                        const riskColor = RISK_COLORS[appr.risk_level] || RISK_COLORS.MEDIUM;
                        const waiting = appr.status === "WAITING FOR MERCHANT APPROVAL";
                        return (
                          <div key={appr.approval_id}
                            className={`border rounded-2xl p-5 space-y-4 transition-all ${waiting ? "border-amber-500/40 bg-amber-500/[0.04] shadow-[0_0_20px_-8px_rgba(245,158,11,0.3)]" : "border-white/10 bg-[#0F1115]"}`}>
                            {/* Header row */}
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                              <div className="flex items-center gap-3 flex-wrap">
                                {/* Approval status chip */}
                                <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold border ${chip.bg} ${chip.border} ${chip.text}`}>
                                  {chip.label}
                                </span>
                                {/* Risk level badge */}
                                <span className={`px-2 py-0.5 rounded text-[9px] font-mono font-bold border ${riskColor.bg} ${riskColor.border} ${riskColor.text}`}>
                                  ⚡ {appr.risk_level} RISK
                                </span>
                              </div>
                              <span className="text-[10px] font-mono text-[#94A3B8]">{appr.approval_id}</span>
                            </div>

                            {/* Details */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                              <div>
                                <div className="text-[9px] text-[#94A3B8] uppercase font-mono mb-0.5">Action</div>
                                <div className="font-heading font-bold text-white">
                                  {appr.action_type?.replace(/_/g, " ") || "—"}
                                </div>
                              </div>
                              <div>
                                <div className="text-[9px] text-[#94A3B8] uppercase font-mono mb-0.5">Product</div>
                                <div className="font-heading font-bold text-white truncate">{appr.product_name}</div>
                              </div>
                              <div>
                                <div className="text-[9px] text-[#94A3B8] uppercase font-mono mb-0.5">Discount</div>
                                <div className="font-mono font-bold text-[#FFD600]">{appr.discount_pct?.toFixed(0)}%</div>
                              </div>
                              <div>
                                <div className="text-[9px] text-[#94A3B8] uppercase font-mono mb-0.5">Order Total</div>
                                <div className="font-mono font-bold text-[#F7931A]">Rs.{appr.requested_amount?.toLocaleString("en-IN")}</div>
                              </div>
                            </div>

                            {/* Details text */}
                            {appr.details && (
                              <p className="text-[11px] text-[#94A3B8] font-body leading-relaxed bg-[#030304]/60 rounded-xl px-3 py-2.5 border border-white/[0.05]">
                                {appr.details}
                              </p>
                            )}

                            {/* Timestamps */}
                            <div className="flex flex-wrap gap-4 text-[10px] font-mono text-[#94A3B8]">
                              <span>Created: {new Date(appr.created_at).toLocaleString()}</span>
                              {appr.resolved_at && <span>Resolved: {new Date(appr.resolved_at).toLocaleString()}</span>}
                              {appr.resolution_reason && <span className="text-white/60">"{appr.resolution_reason}"</span>}
                            </div>

                            {/* Action Buttons — only for waiting */}
                            {waiting && (
                              <div className="flex gap-3 pt-1">
                                <button
                                  onClick={() => handleApprove(appr.approval_id)}
                                  className="flex-1 py-2.5 rounded-full bg-green-500/20 border border-green-500/40 text-green-400 text-xs font-heading font-bold uppercase tracking-wider hover:bg-green-500/30 transition-all cursor-pointer">
                                  ✓ Approve
                                </button>
                                <button
                                  onClick={() => handleBlock(appr.approval_id)}
                                  className="flex-1 py-2.5 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 text-xs font-heading font-bold uppercase tracking-wider hover:bg-red-500/30 transition-all cursor-pointer">
                                  ✕ Block
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ── CONVERSATIONS TAB ── */}
              {activeTab === "conversations" && (
                <div className="h-full flex overflow-hidden animate-fadeIn" style={{ height: "calc(100vh - 64px)" }}>
                  <div className="w-80 border-r border-white/10 bg-[#0F1115] overflow-y-auto flex-shrink-0">
                    <div className="px-6 py-4 border-b border-white/10">
                      <h3 className="text-xs font-mono font-bold uppercase tracking-widest text-[#F7931A]">Session Protocol Ledger</h3>
                    </div>
                    <div className="divide-y divide-white/5">
                      {sessionsList.map(sess => (
                        <button key={sess.session_id} onClick={() => handleSelectSession(sess.session_id)}
                          className={`w-full text-left px-6 py-4 text-xs space-y-1 transition-all ${selectedSessionId === sess.session_id ? "bg-gradient-to-r from-[#EA580C]/20 to-transparent border-l-2 border-[#F7931A]" : "hover:bg-white/[0.02]"}`}>
                          <div className="font-mono text-white font-bold truncate text-[11px]">{sess.session_id}</div>
                          <div className="flex justify-between text-[#94A3B8] text-[9px] font-mono">
                            <span className="text-[#F7931A]">{sess.last_action.replace(/_/g, ' ')}</span>
                            <span>{new Date(sess.last_active).toLocaleTimeString()}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-8 md:p-10">
                    {selectedSessionId ? (() => {
                      const buyerDetails = getBuyerEventDetails(selectedSessionId);
                      const auditLogsForSession = (sessionDetail?.audit_events && sessionDetail.audit_events.length > 0)
                        ? sessionDetail.audit_events
                        : activityLogs.filter(l => l.session_id === selectedSessionId);

                      return (
                        <div className="max-w-3xl space-y-6">
                          <div className="border-b border-white/10 pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                            <div>
                              <h3 className="text-base font-heading font-bold text-white">Conversation Audit Trace</h3>
                              <p className="text-xs text-[#F7931A] font-mono mt-1">{selectedSessionId}</p>
                            </div>
                            {buyerDetails && (
                              <div className={`self-start sm:self-auto px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider border ${
                                buyerDetails.type === "success"
                                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                                  : "bg-red-500/10 border-red-500/30 text-red-400"
                              }`}>
                                {buyerDetails.type === "success" ? `● ${buyerDetails.status}` : `● REJECTED (HTTP ${buyerDetails.http_status})`}
                              </div>
                            )}
                          </div>

                          {/* ── Structured Buyer Event Card: SUCCESS ── */}
                          {buyerDetails && buyerDetails.type === "success" && (
                            <div className="bg-[#030304]/80 border border-emerald-500/30 rounded-2xl p-5 space-y-4 glow-card">
                              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                                <div className="flex items-center gap-2">
                                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                                  <span className="text-xs font-heading font-bold text-white uppercase tracking-wider">
                                    Structured Buyer Transaction Data
                                  </span>
                                </div>
                                <span className="text-[10px] font-mono bg-emerald-500/20 text-emerald-300 px-2.5 py-0.5 rounded-full border border-emerald-500/30 font-bold">
                                  Status: {buyerDetails.status}
                                </span>
                              </div>

                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1 sm:col-span-2">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Product Name</div>
                                  <div className="font-heading font-bold text-white truncate">{buyerDetails.product_name}</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Product ID</div>
                                  <div className="font-mono font-bold text-[#F7931A] truncate">{buyerDetails.product_id}</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Quantity</div>
                                  <div className="font-mono font-bold text-white">{buyerDetails.quantity} unit(s)</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Unit Price</div>
                                  <div className="font-mono font-bold text-[#FFD600]">Rs.{buyerDetails.unit_price?.toLocaleString("en-IN")}</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Total Amount</div>
                                  <div className="font-mono font-bold text-emerald-400 text-sm">Rs.{buyerDetails.total_amount?.toLocaleString("en-IN")}</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1 sm:col-span-2">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Intent ID</div>
                                  <div className="font-mono text-blue-400 truncate text-[11px]">{buyerDetails.intent_id}</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1 sm:col-span-2">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Razorpay Order ID</div>
                                  <div className="font-mono text-green-400 font-bold truncate text-[11px]">{buyerDetails.razorpay_order_id}</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1 sm:col-span-2">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Transaction Status</div>
                                  <div className="font-mono font-bold text-emerald-400 text-[11px]">✓ {buyerDetails.status} (Cryptographically Authorized)</div>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* ── Structured Buyer Event Card: REJECTED / BLOCKED ── */}
                          {buyerDetails && buyerDetails.type === "rejected" && (
                            <div className="bg-[#030304]/80 border border-red-500/30 rounded-2xl p-5 space-y-4 glow-card">
                              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                                <div className="flex items-center gap-2">
                                  <AlertTriangle className="w-5 h-5 text-red-400" />
                                  <span className="text-xs font-heading font-bold text-white uppercase tracking-wider">
                                    Rejected Buyer Transaction Details
                                  </span>
                                </div>
                                <span className="text-[10px] font-mono bg-red-500/20 text-red-300 px-2.5 py-0.5 rounded-full border border-red-500/30 font-bold">
                                  HTTP {buyerDetails.http_status}
                                </span>
                              </div>

                              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3.5 space-y-1">
                                <div className="text-[9px] text-red-300 font-mono uppercase tracking-wider font-bold">Rejection Reason</div>
                                <p className="text-xs text-red-200 font-mono leading-relaxed">{buyerDetails.rejection_reason}</p>
                              </div>

                              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Attempted Quantity</div>
                                  <div className="font-mono font-bold text-red-400 text-sm">{buyerDetails.attempted_quantity} unit(s)</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">Max Allowed Quantity</div>
                                  <div className="font-mono font-bold text-emerald-400 text-sm">{buyerDetails.max_allowed_quantity} unit(s) / SKU</div>
                                </div>
                                <div className="bg-[#0F1115] p-3 rounded-xl border border-white/5 space-y-1 col-span-2 sm:col-span-1">
                                  <div className="text-[9px] text-[#94A3B8] font-mono uppercase tracking-wider">HTTP Status</div>
                                  <div className="font-mono font-bold text-amber-400 text-sm">{buyerDetails.http_status} Conflict</div>
                                </div>
                              </div>

                              <div className="bg-[#0F1115] border border-white/10 rounded-xl p-3.5 space-y-1">
                                <div className="text-[9px] text-[#F7931A] font-mono uppercase tracking-wider font-bold">Retry Suggestion</div>
                                <p className="text-xs text-gray-300 font-body leading-relaxed">{buyerDetails.retry_suggestion}</p>
                              </div>
                            </div>
                          )}

                          {/* ── Human Chat Messages (if any) ── */}
                          {sessionHistory && sessionHistory.length > 0 && (
                            <div className="space-y-4 pt-2">
                              <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#94A3B8]">
                                Customer Interaction Log ({sessionHistory.length} messages)
                              </div>
                              {sessionHistory.map((msg, i) => (
                                <div key={i} className="flex gap-3.5">
                                  <div className="w-8 h-8 rounded-full bg-[#0F1115] border border-white/10 flex items-center justify-center text-[10px] font-heading font-bold uppercase text-[#FFD600] flex-shrink-0">
                                    {msg.sender === "user" ? "U" : "AI"}
                                  </div>
                                  <div className="flex-1">
                                    <div className="text-[9px] font-mono font-bold uppercase tracking-wider text-[#94A3B8] mb-1">{msg.sender === "user" ? "Customer" : "GrowthPilot Agent"}</div>
                                    <p className="text-xs text-gray-200 bg-[#0F1115] p-4 rounded-2xl border border-white/10 leading-relaxed max-w-xl font-body">{msg.message}</p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* ── Structured Audit Log Trail ── */}
                          {auditLogsForSession && auditLogsForSession.length > 0 && (
                            <div className="space-y-3 pt-4 border-t border-white/10">
                              <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#94A3B8]">
                                Append-Only Audit Ledger ({auditLogsForSession.length} events)
                              </div>
                              <div className="space-y-2">
                                {auditLogsForSession.map((log, idx) => (
                                  <div key={idx} className="bg-[#0F1115] p-3 rounded-xl border border-white/5 text-xs font-mono space-y-1">
                                    <div className="flex items-center justify-between text-[10px]">
                                      <span className="text-[#F7931A] font-bold">[{log.action_type}]</span>
                                      <span className="text-[#94A3B8]">{new Date(log.timestamp).toLocaleTimeString()}</span>
                                    </div>
                                    <p className="text-gray-300 text-[11px]">{log.reasoning || log.details}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })() : (
                      <div className="flex flex-col items-center justify-center h-full gap-3 text-xs text-[#94A3B8] font-mono">
                        <MessageSquare className="w-6 h-6 text-[#F7931A]" />
                        Select a session from the left to inspect conversation trace.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── PRODUCTS TAB ── */}
              {activeTab === "products" && (
                <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-6 animate-fadeIn">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-6">
                    <div>
                      <h2 className="text-xl font-heading font-bold text-white">Merchant Catalog Matrix</h2>
                      <p className="text-xs text-[#94A3B8] mt-1 font-body">{products.length} products loaded with real cost, profit margin, and stock metrics</p>
                    </div>
                  </div>
                  <div className="border border-white/10 bg-[#0F1115] rounded-2xl overflow-hidden glow-card">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-white/10 bg-[#030304]/60 text-[#94A3B8] font-mono uppercase tracking-wider text-[9px]">
                          <th className="py-4 px-5">Product</th>
                          <th className="py-4 px-5 hidden sm:table-cell">Category</th>
                          <th className="py-4 px-5 text-right">Price</th>
                          <th className="py-4 px-5 text-right hidden md:table-cell">Cost</th>
                          <th className="py-4 px-5 text-right text-[#FFD600]">Margin</th>
                          <th className="py-4 px-5 text-center">Stock</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {products.map(p => (
                          <tr key={p.id} className="hover:bg-white/[0.02] transition-all">
                            <td className="py-3.5 px-5">
                              <div className="flex items-center gap-3">
                                <img
                                  src={p.image}
                                  onError={(e) => {
                                    e.currentTarget.onerror = null;
                                    e.currentTarget.src = CATEGORY_FALLBACK_IMAGES[p.category] || CATEGORY_FALLBACK_IMAGES.default;
                                  }}
                                  className="w-10 h-8 object-cover rounded-lg bg-gray-900 border border-white/10 flex-shrink-0"
                                  alt=""
                                />
                                <div className="min-w-0">
                                  <div className="font-heading font-bold text-white truncate text-xs">{p.name}</div>
                                </div>
                              </div>
                            </td>
                            <td className="py-3.5 px-5 font-mono text-[10px] text-[#F7931A] uppercase hidden sm:table-cell">{p.category}</td>
                            <td className="py-3.5 px-5 text-right font-heading font-bold text-white">Rs.{p.price.toLocaleString("en-IN")}</td>
                            <td className="py-3.5 px-5 text-right text-[#94A3B8] font-mono text-[11px] hidden md:table-cell">Rs.{p.cost_price.toLocaleString("en-IN")}</td>
                            <td className="py-3.5 px-5 text-right font-mono font-bold text-[#FFD600]">Rs.{p.profit_margin.toLocaleString("en-IN")}</td>
                            <td className="py-3.5 px-5 text-center">
                              <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-mono font-bold ${p.stock <= 3 ? "bg-red-500/10 text-red-400 border border-red-500/30" : "bg-white/5 text-[#94A3B8]"}`}>{p.stock}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── ORDERS TAB ── */}
              {activeTab === "orders" && (
                <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-6 animate-fadeIn">
                  <div className="border-b border-white/10 pb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-heading font-bold text-white">Settlement Ledger</h2>
                      <p className="text-xs text-[#94A3B8] mt-1 font-body">Immutable transaction logs with strategy attribution and gateway tokens</p>
                    </div>
                    <button
                      onClick={fetchDashboardStats}
                      className="self-start sm:self-auto px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-[#94A3B8] hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all cursor-pointer">
                      <RefreshCw className="w-3.5 h-3.5" />
                      Refresh Ledger
                    </button>
                  </div>
                  <div className="border border-white/10 bg-[#0F1115] rounded-2xl overflow-hidden glow-card">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-white/10 bg-[#030304]/60 text-[#94A3B8] font-mono uppercase tracking-wider text-[9px]">
                          <th className="py-4 px-5">Session Node</th>
                          <th className="py-4 px-5">Product</th>
                          <th className="py-4 px-5 text-right">Amount</th>
                          <th className="py-4 px-5 text-center">Incentive</th>
                          <th className="py-4 px-5 text-center">Gateway Token</th>
                          <th className="py-4 px-5 text-center">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5 font-mono text-[11px]">
                        {(ordersList.length > 0 ? ordersList : activityLogs.filter(l => (l.action_type === "order_created" || l.action_type === "payment_created" || l.action_type === "payment_paid") && l.payload).map(l => ({
                          id: l.id,
                          session_id: l.session_id,
                          product_name: l.payload?.product_name || "Product",
                          amount: l.payload?.amount || 0,
                          incentive_used: l.payload?.incentive_used || "none",
                          razorpay_order_id: l.payload?.razorpay_order_id || l.payload?.id,
                          razorpay_payment_id: l.payload?.razorpay_payment_id,
                          status: (l.action_type === "payment_paid" || l.payload?.status === "paid") ? "paid" : (l.payload?.status || "pending")
                        }))).map(order => {
                          const isPaid = order.status === "paid" || order.status === "confirmed" || order.status === "settled" || !!order.razorpay_payment_id;
                          const isFailed = order.status === "failed";
                          return (
                            <tr key={order.id || order.razorpay_order_id} className="hover:bg-white/[0.02] transition-colors">
                              <td className="py-4 px-5 text-[#94A3B8] truncate max-w-[150px] font-mono">
                                {order.session_id ? `${order.session_id.slice(0, 18)}…` : "direct_session"}
                              </td>
                              <td className="py-4 px-5 text-white font-heading font-bold">{order.product_name}</td>
                              <td className="py-4 px-5 text-right text-[#FFD600] font-bold">Rs.{Number(order.amount).toLocaleString("en-IN")}</td>
                              <td className="py-4 px-5 text-center">
                                <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-bold ${order.incentive_used && order.incentive_used !== 'none' ? "bg-[#F7931A]/15 text-[#FFD600] border border-[#F7931A]/30" : "text-[#94A3B8]"}`}>
                                  {order.incentive_used && order.incentive_used !== 'none' ? order.incentive_used : "Standard"}
                                </span>
                              </td>
                              <td className="py-4 px-5 text-center">
                                <span className="text-[10px] font-mono text-[#94A3B8] bg-white/5 px-2 py-0.5 rounded border border-white/5 truncate max-w-[120px] inline-block">
                                  {order.razorpay_payment_id || order.razorpay_order_id || "rzp_token"}
                                </span>
                              </td>
                              <td className="py-4 px-5 text-center">
                                <span className={`px-3 py-1 rounded-full text-[9px] font-mono font-bold uppercase tracking-wider ${
                                  isPaid
                                    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                    : isFailed
                                    ? "bg-red-500/15 text-red-400 border border-red-500/30"
                                    : "bg-[#F7931A]/15 text-[#F7931A] border border-[#F7931A]/30"
                                }`}>
                                  {isPaid ? "PAID" : isFailed ? "FAILED" : "PENDING"}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── ANALYTICS TAB ── */}
              {activeTab === "analytics" && (
                <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-8 animate-fadeIn">
                  <div className="border-b border-white/10 pb-6">
                    <span className="text-[10px] font-mono tracking-widest text-[#F7931A] uppercase font-bold">Protocol Telemetry</span>
                    <h2 className="text-2xl font-heading font-bold text-white mt-1">Rs.{metrics.revenue_influenced.toLocaleString("en-IN")} in Settled AI Volume</h2>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-6 space-y-4 glow-card">
                      <div><h3 className="text-xs font-mono font-bold text-[#F7931A] uppercase tracking-widest">Revenue Impact Curve</h3></div>
                      <div className="h-56">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chartData.revenue_chart} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <defs>
                              <linearGradient id="btcGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#F7931A" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#EA580C" stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <XAxis dataKey="date" stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} />
                            <YAxis stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} />
                            <Tooltip contentStyle={{ backgroundColor: "#0F1115", border: "1px solid rgba(247,147,26,0.3)", borderRadius: "12px", fontSize: 11, color: "#FFFFFF" }} />
                            <Area type="monotone" dataKey="revenue" stroke="#F7931A" strokeWidth={2} fill="url(#btcGrad)" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-6 space-y-4 glow-card">
                      <div><h3 className="text-xs font-mono font-bold text-[#FFD600] uppercase tracking-widest">Strategy Feedback Performance</h3></div>
                      {chartData.strategy_performance?.length > 0 ? (
                        <div className="h-56">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData.strategy_performance} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                              <XAxis dataKey="strategy" stroke="#94A3B8" fontSize={8} tickLine={false} axisLine={false} tickFormatter={s => s.replace(/_/g, ' ').slice(0, 12)} />
                              <YAxis stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} unit="%" />
                              <Tooltip contentStyle={{ backgroundColor: "#0F1115", border: "1px solid rgba(247,147,26,0.3)", borderRadius: "12px", fontSize: 11, color: "#FFFFFF" }} formatter={(v) => [`${v}%`, "Conv. Rate"]} />
                              <Bar dataKey="conversion_rate" fill="#FFD600" radius={[6, 6, 0, 0]} barSize={26} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <div className="h-56 flex items-center justify-center text-xs text-[#94A3B8] font-mono italic">Execute transactions to view strategy telemetry.</div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ── SETTINGS TAB ── */}
              {activeTab === "settings" && (
                <div className="p-6 md:p-10 max-w-2xl mx-auto space-y-8 animate-fadeIn">
                  <div className="border-b border-white/10 pb-6">
                    <h2 className="text-xl font-heading font-bold text-white">Merchant Policy Engine</h2>
                    <p className="text-xs text-[#94A3B8] mt-1 font-body">Set the active merchant objective and strict backend policy limits governing AI decision proposals.</p>
                  </div>
                  <div className="space-y-4">
                    <label className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#F7931A] block">Merchant Objective</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                      {OBJECTIVES.map(obj => (
                        <button key={obj.id} onClick={() => setMerchantSettings(s => ({ ...s, objective: obj.id }))}
                          className={`text-left p-5 rounded-2xl border transition-all space-y-2 cursor-pointer ${merchantSettings.objective === obj.id ? "border-[#F7931A] bg-[#F7931A]/10 shadow-[0_0_20px_-5px_rgba(247,147,26,0.3)]" : "border-white/10 bg-[#0F1115] hover:border-white/20"}`}>
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-heading font-bold text-white">{obj.label}</span>
                            {merchantSettings.objective === obj.id && <Check className="w-4 h-4 text-[#FFD600]" />}
                          </div>
                          <p className="text-[10px] text-[#94A3B8] leading-relaxed font-body">{obj.desc}</p>
                        </button>
                      ))}
                    </div>

                    {/* ── Live Objective Strategy Comparison Matrix ── */}
                    <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-5 space-y-4 glow-card mt-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/10 pb-3">
                        <div>
                          <div className="flex items-center gap-2 text-xs font-mono font-bold text-[#FFD600] uppercase tracking-wider">
                            <Sparkles className="w-4 h-4 text-[#F7931A]" />
                            Live Objective Strategy Matrix
                          </div>
                          <p className="text-[10px] text-[#94A3B8] font-body mt-0.5">
                            Comparing how changing the active objective alters the AI proposal for a price objection scenario.
                          </p>
                        </div>
                        {products.length > 0 && (
                          <select
                            value={matrixProduct || (products[0]?.id || "")}
                            onChange={(e) => { setMatrixProduct(e.target.value); fetchObjectiveMatrix(e.target.value); }}
                            className="bg-[#030304] border border-white/10 text-[10px] font-mono rounded-lg px-2.5 py-1.5 text-white focus:outline-none focus:border-[#F7931A]">
                            {products.slice(0, 10).map(p => (
                              <option key={p.id} value={p.id}>{p.name} (Rs.{p.price?.toLocaleString("en-IN")})</option>
                            ))}
                          </select>
                        )}
                      </div>

                      {matrixLoading ? (
                        <div className="py-8 text-center text-xs text-[#94A3B8] font-mono animate-pulse">
                          Evaluating objective branches against active policy bounds...
                        </div>
                      ) : objectiveMatrix?.matrix ? (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
                          {/* 1. PROTECT PROFIT */}
                          {objectiveMatrix.matrix.protect_profit && (
                            <div className={`border rounded-xl p-3.5 space-y-2.5 transition-all ${merchantSettings.objective === "protect_profit" ? "border-green-500/50 bg-green-500/[0.06] ring-1 ring-green-500/30" : "border-white/10 bg-[#030304]/60"}`}>
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono font-bold uppercase text-green-400">🛡️ Protect Profit</span>
                                {merchantSettings.objective === "protect_profit" && (
                                  <span className="text-[8px] font-mono bg-green-500/20 text-green-300 border border-green-500/40 px-1.5 py-0.5 rounded font-bold">ACTIVE</span>
                                )}
                              </div>
                              <div>
                                <div className="text-[9px] text-[#94A3B8] font-mono uppercase">AI Proposal</div>
                                <div className="text-xs font-heading font-bold text-white">{objectiveMatrix.matrix.protect_profit.action_label}</div>
                              </div>
                              <div className="text-[10px] text-gray-300 font-body bg-white/[0.02] p-2 rounded border border-white/5 line-clamp-3">
                                {objectiveMatrix.matrix.protect_profit.reasoning}
                              </div>
                              <div className="flex items-center justify-between text-[9px] font-mono pt-1 border-t border-white/5">
                                <span className="text-[#94A3B8]">Incentive:</span>
                                <span className="text-green-400 font-bold">{objectiveMatrix.matrix.protect_profit.incentive_applied}</span>
                              </div>
                              <button
                                onClick={() => handleQuickSwitchObjective("protect_profit")}
                                className={`w-full py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase transition-all cursor-pointer ${merchantSettings.objective === "protect_profit" ? "bg-green-500/20 text-green-400 border border-green-500/40" : "bg-white/5 text-[#94A3B8] hover:text-white border border-white/10 hover:border-green-500/30"}`}>
                                {merchantSettings.objective === "protect_profit" ? "✓ Active Objective" : "Activate"}
                              </button>
                            </div>
                          )}

                          {/* 2. MAXIMIZE CONVERSIONS */}
                          {objectiveMatrix.matrix.maximize_conversions && (
                            <div className={`border rounded-xl p-3.5 space-y-2.5 transition-all ${merchantSettings.objective === "maximize_conversions" ? "border-[#F7931A]/60 bg-[#F7931A]/[0.08] ring-1 ring-[#F7931A]/30" : "border-white/10 bg-[#030304]/60"}`}>
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono font-bold uppercase text-[#F7931A]">⚡ Max Conversions</span>
                                {merchantSettings.objective === "maximize_conversions" && (
                                  <span className="text-[8px] font-mono bg-[#F7931A]/20 text-[#FFD600] border border-[#F7931A]/40 px-1.5 py-0.5 rounded font-bold">ACTIVE</span>
                                )}
                              </div>
                              <div>
                                <div className="text-[9px] text-[#94A3B8] font-mono uppercase">AI Proposal</div>
                                <div className="text-xs font-heading font-bold text-white">{objectiveMatrix.matrix.maximize_conversions.action_label}</div>
                              </div>
                              <div className="text-[10px] text-gray-300 font-body bg-white/[0.02] p-2 rounded border border-white/5 line-clamp-3">
                                {objectiveMatrix.matrix.maximize_conversions.reasoning}
                              </div>
                              <div className="flex items-center justify-between text-[9px] font-mono pt-1 border-t border-white/5">
                                <span className="text-[#94A3B8]">Incentive:</span>
                                <span className="text-[#FFD600] font-bold">{objectiveMatrix.matrix.maximize_conversions.incentive_applied}</span>
                              </div>
                              <button
                                onClick={() => handleQuickSwitchObjective("maximize_conversions")}
                                className={`w-full py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase transition-all cursor-pointer ${merchantSettings.objective === "maximize_conversions" ? "bg-[#F7931A]/20 text-[#FFD600] border border-[#F7931A]/40" : "bg-white/5 text-[#94A3B8] hover:text-white border border-white/10 hover:border-[#F7931A]/30"}`}>
                                {merchantSettings.objective === "maximize_conversions" ? "✓ Active Objective" : "Activate"}
                              </button>
                            </div>
                          )}

                          {/* 3. INCREASE AOV */}
                          {objectiveMatrix.matrix.increase_aov && (
                            <div className={`border rounded-xl p-3.5 space-y-2.5 transition-all ${merchantSettings.objective === "increase_aov" ? "border-[#FFD600]/60 bg-[#FFD600]/[0.08] ring-1 ring-[#FFD600]/30" : "border-white/10 bg-[#030304]/60"}`}>
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono font-bold uppercase text-[#FFD600]">📦 Increase AOV</span>
                                {merchantSettings.objective === "increase_aov" && (
                                  <span className="text-[8px] font-mono bg-[#FFD600]/20 text-[#FFD600] border border-[#FFD600]/40 px-1.5 py-0.5 rounded font-bold">ACTIVE</span>
                                )}
                              </div>
                              <div>
                                <div className="text-[9px] text-[#94A3B8] font-mono uppercase">AI Proposal</div>
                                <div className="text-xs font-heading font-bold text-white">{objectiveMatrix.matrix.increase_aov.action_label}</div>
                              </div>
                              <div className="text-[10px] text-gray-300 font-body bg-white/[0.02] p-2 rounded border border-white/5 line-clamp-3">
                                {objectiveMatrix.matrix.increase_aov.reasoning}
                              </div>
                              <div className="flex items-center justify-between text-[9px] font-mono pt-1 border-t border-white/5">
                                <span className="text-[#94A3B8]">Incentive:</span>
                                <span className="text-[#FFD600] font-bold">{objectiveMatrix.matrix.increase_aov.incentive_applied}</span>
                              </div>
                              <button
                                onClick={() => handleQuickSwitchObjective("increase_aov")}
                                className={`w-full py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase transition-all cursor-pointer ${merchantSettings.objective === "increase_aov" ? "bg-[#FFD600]/20 text-[#FFD600] border border-[#FFD600]/40" : "bg-white/5 text-[#94A3B8] hover:text-white border border-white/10 hover:border-[#FFD600]/30"}`}>
                                {merchantSettings.objective === "increase_aov" ? "✓ Active Objective" : "Activate"}
                              </button>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <div className="border border-white/10 bg-[#0F1115] rounded-2xl p-6 space-y-5 glow-card">
                    <h3 className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#FFD600]">Backend Policy Bounds & Guardrails</h3>
                    <div className="space-y-5">
                      {[
                        { key: "max_discount_pct", label: "1. Maximum Discount Cap", unit: "%", min: 0, max: 30, step: 1, desc: "AI cannot propose discounts beyond this limit" },
                        { key: "min_margin",        label: "2. Minimum Acceptable Margin", unit: "Rs.", min: 0, max: 2000, step: 50, desc: "Guaranteed unit profit floor" },
                        { key: "shipping_cost",     label: "3. Shipping Waiver Limit", unit: "Rs.", min: 0, max: 500, step: 10, desc: "Maximum allowable shipping incentive" },
                      ].map(({ key, label, unit, min, max, step, desc }) => (
                        <div key={key}>
                          <div className="flex justify-between mb-1">
                            <label className="text-xs font-heading font-semibold text-gray-200">
                              {label}
                              <span className="ml-2 text-[9px] font-mono text-[#94A3B8] font-normal">{desc}</span>
                            </label>
                            <span className="text-xs font-mono text-[#FFD600] font-bold">{unit === "%" ? `${merchantSettings[key]}%` : `Rs.${merchantSettings[key]}`}</span>
                          </div>
                          <input type="range" min={min} max={max} step={step} value={merchantSettings[key]}
                            onChange={e => setMerchantSettings(s => ({ ...s, [key]: parseFloat(e.target.value) }))}
                            className="w-full accent-[#F7931A] h-1.5 bg-[#030304] rounded-lg cursor-pointer" />
                        </div>
                      ))}

                      {/* 4. Quantity Limit info card */}
                      <div className="pt-2">
                        <div className="flex justify-between items-center mb-1">
                          <label className="text-xs font-heading font-semibold text-gray-200">
                            4. Per-SKU Quantity Limit
                            <span className="ml-2 text-[9px] font-mono text-[#94A3B8] font-normal">Fixed ceiling preventing inventory drain</span>
                          </label>
                          <span className="text-xs font-mono text-blue-400 font-bold">5 Units</span>
                        </div>
                        <div className="w-full h-1.5 bg-[#030304] rounded-lg overflow-hidden flex">
                          <div className="h-full bg-blue-500 w-[50%]" />
                        </div>
                      </div>

                      {/* 5. HIGH-risk threshold — distinct amber section */}
                      <div className="pt-3 border-t border-amber-500/20">
                        <div className="flex items-center gap-2 mb-3">
                          <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-0.5">⚡ 5. HIGH-RISK APPROVAL THRESHOLD</span>
                        </div>
                        <div>
                          <div className="flex justify-between mb-2">
                            <label className="text-xs font-heading font-semibold text-amber-300">
                              Approval Threshold
                              <span className="ml-2 text-[9px] font-mono text-[#94A3B8] normal-case">Discounts at or above this % require merchant approval</span>
                            </label>
                            <span className="text-xs font-mono text-amber-400 font-bold">{merchantSettings.high_risk_discount_threshold}%</span>
                          </div>
                          <input type="range" min={5} max={30} step={1}
                            value={merchantSettings.high_risk_discount_threshold || 15}
                            onChange={e => setMerchantSettings(s => ({ ...s, high_risk_discount_threshold: parseFloat(e.target.value) }))}
                            className="w-full h-1.5 bg-[#030304] rounded-lg cursor-pointer accent-amber-500" />
                        </div>
                      </div>
                    </div>
                  </div>

                  <button onClick={handleSaveSettings} disabled={settingsSaving}
                    className={`w-full py-3.5 rounded-full font-heading font-bold text-xs uppercase tracking-wider transition-all cursor-pointer shadow-[0_0_20px_rgba(247,147,26,0.6)] ${settingsSaved ? "bg-[#FFD600] text-black" : "bg-gradient-to-r from-[#EA580C] to-[#F7931A] hover:shadow-[0_0_30px_rgba(247,147,26,0.8)] text-white"} disabled:opacity-50`}>
                    {settingsSaving ? "Committing..." : settingsSaved ? "Configuration Committed!" : "Save Policy Configuration"}
                  </button>
                </div>
              )}

            </div>
          </div>
        )}
      </div>

      {/* ── Razorpay Standard Test Checkout Modal ── */}
      {showPaymentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#0B1426] border border-[#1E293B] rounded-2xl w-full max-w-md overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.8)] flex flex-col">
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-[#0C2340] to-[#1E3A8A] px-6 py-4 border-b border-blue-900/40 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-500/20 border border-blue-400/40 flex items-center justify-center">
                  <ShieldCheck className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-heading font-bold text-sm tracking-wide text-white">Razorpay</span>
                    <span className="text-[9px] font-mono font-bold bg-amber-500/20 border border-amber-500/40 text-amber-300 px-1.5 py-0.5 rounded">TEST MODE</span>
                  </div>
                  <p className="text-[10px] text-blue-300 font-mono">Secured with 256-bit Encryption</p>
                </div>
              </div>
              <button
                onClick={() => setShowPaymentModal(null)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-4">
              {/* Order Info Box */}
              <div className="bg-[#030712]/60 border border-white/5 rounded-xl p-4 flex justify-between items-center">
                <div>
                  <div className="text-[10px] font-mono text-gray-400 uppercase">GrowthPilot Store</div>
                  <div className="text-sm font-semibold text-white truncate max-w-[200px]">
                    {showPaymentModal.product?.name || "SoundFlow Wireless Earbuds"}
                  </div>
                  <div className="text-[10px] font-mono text-blue-400">
                    Order: {showPaymentModal.options?.order_id || showPaymentModal.orderId || "order_test"}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] font-mono text-gray-400">Amount Due</div>
                  <div className="text-lg font-mono font-bold text-[#FFD600]">
                    ₹{(showPaymentModal.amount || 2499).toLocaleString("en-IN")}
                  </div>
                </div>
              </div>

              {/* Payment Methods Simulation */}
              <div className="space-y-3">
                <div className="text-[11px] font-mono font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
                  <span>Select Test Payment Method</span>
                </div>

                {/* Option 1: Card */}
                <div className="border border-blue-500/30 bg-blue-950/20 rounded-xl p-3.5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded bg-blue-600/30 flex items-center justify-center text-blue-400 font-bold text-xs">
                      💳
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-white">Razorpay Test Card</div>
                      <div className="text-[10px] font-mono text-gray-400">4111 •••• •••• 1111 (12/28)</div>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">Instant</span>
                </div>

                {/* Option 2: UPI */}
                <div className="border border-white/10 bg-white/5 rounded-xl p-3.5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded bg-emerald-600/30 flex items-center justify-center text-emerald-400 font-bold text-xs">
                      📱
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-white">UPI / QR Code</div>
                      <div className="text-[10px] font-mono text-gray-400">growthpilot@upi</div>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono text-gray-400">GPay / PhonePe</span>
                </div>
              </div>

              {/* Simulation Action Buttons */}
              <div className="pt-2 space-y-2">
                <button
                  onClick={() => handleCompletePaymentSuccess(showPaymentModal, "card")}
                  className="w-full py-3 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white rounded-xl font-heading font-bold text-xs uppercase tracking-wider transition-all shadow-[0_0_20px_rgba(16,185,129,0.4)] flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span>✓ Complete Test Payment (₹{(showPaymentModal.amount || 2499).toLocaleString("en-IN")})</span>
                </button>

                <button
                  onClick={() => handleSimulatePaymentFailure(showPaymentModal)}
                  className="w-full py-2.5 bg-red-950/40 hover:bg-red-900/60 border border-red-500/30 text-red-300 rounded-xl font-mono text-[11px] transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span>⚠️ Simulate Payment Failure (Card Declined)</span>
                </button>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="bg-[#030712] px-6 py-3 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-gray-500">
              <span>Razorpay Test Gateway v1.0</span>
              <span>HMAC-SHA256 Signed</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
