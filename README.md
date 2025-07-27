# Adaptive-Load-Balanced-Crowdsourced-Troubleshooting-System

## 🧠 Overview

In today’s digital-first world, users rely heavily on support systems when facing technical issues — but most helpdesk platforms suffer from centralized bottlenecks, overloaded experts, and zero fault tolerance. As user bases scale across regions and time zones, traditional support models begin to collapse under pressure, leading to slow response times, poor user experience, and unresolved issues.

**This project proposes a new approach.**

The **Adaptive Load-Balanced Crowdsourced Troubleshooting System** is a **region-aware, distributed support platform** designed to intelligently match user-reported issues with qualified experts in real time. Built using **FastAPI, MongoDB, and Docker**, the system is architected as **multiple independent service nodes** (North, South, East, West), each capable of handling user submissions, expert resolutions, and inter-node rerouting.

Instead of static expert allocation, the system uses a **multi-factor scoring engine** that considers:
- 🔍 **Skill Match** (via keyword or semantic similarity)
- 💡 **Availability** (online status)
- ⭐ **Trust Score** (historical feedback, updated dynamically)
- ⚖️ **Current Load** (to prevent expert overload)

Experts can **accept or reject tasks**, and the system supports **greedy fallback logic** to reroute unresolved issues to alternate experts or peer nodes. Once assigned, users and experts can communicate through a **real-time chat system** and complete issue resolution collaboratively.

To ensure accountability and improvement, a **two-way feedback system** is implemented — users rate experts, and trust scores evolve accordingly. An **admin dashboard** offers full visibility into expert performance, pending verifications, and regional load stats.

> 🚀 By combining the scalability of distributed systems with the flexibility of crowdsourced expert models, this platform delivers **real-time**, **resilient**, and **intelligent troubleshooting support** — without relying on centralized control.

---

## 🧩 Project Structure

```
distributed_troubleshooter/
├── app/
│   ├── auth/                    # Login/authentication logic
│   ├── routes/                  # API endpoints for users, experts, admin
│   ├── services/                # Core backend services
│   │   ├── config.py            # MongoDB connection + app settings
│   │   ├── init_db.py           # MongoDB initialization
│   │   ├── main.py              # FastAPI app entrypoint
│   │   └── websocket_manager.py # (Optional) WebSocket logic
├── frontend/
│   ├── js/                      # JS for login, quiz, dashboard logic
│   ├── admin_dashboard.html     # Admin view to verify experts, view stats
│   ├── admin_login.html         # Static admin login page
│   ├── expert_dashboard.html    # Expert issue handling & chat
│   ├── user_dashboard.html      # User issue submission & tracking
│   ├── profile.html             # Profile views (user/expert)
│   ├── quiz.html                # Optional expert quiz
│   └── index.html               # Landing / login / signup
├── docker-compose.yml           # Simulated multi-node deployment
├── requirements.txt             # Python dependencies
└── README.md
```

---

## ⚙️ How It Works

### 🧑‍💻 1. User Flow
- Registers with region tag (North, South, East, West)
- Submits a technical issue with title, description, urgency, and category
- Issue is queued and passed to the **Matching Engine**

### 🧠 2. Matching Engine
- Computes composite score for each expert:
  ```
  Score = (w1 × Skill Match) + (w2 × Trust Score) + (w3 × Availability) + (w4 × Inverse Load)
  ```
- Uses keyword or Sentence-BERT-based semantic similarity
- If no local expert available → retry logic + reroute to peer region via REST

### 🧑‍🏫 3. Expert Flow
- Registers with qualifications (optionally takes quiz)
- Must be verified by Admin
- Can:
  - Accept / Reject issues
  - Chat with user
  - Submit resolution and mark issue done
  - Receive trust score from feedback

### 🛡️ 4. Admin Role
- Static login
- Approves expert registrations
- Monitors:
  - Region-wise expert availability
  - Pending issues
  - Trust score trends

### 💬 5. Real-Time Chat & Feedback
- AJAX-based chat between expert and user
- Chat per issue, saved in DB
- On resolution:
  - Both user and expert must confirm completion
  - User gives star-based rating + optional comment
  - Trust score is updated using EMA

---

## 🔄 Distributed Deployment

The system is deployed across 4 **simulated regional nodes**:

- Each node runs its own FastAPI app + MongoDB
- Docker Compose handles multi-container orchestration
- RESTful APIs enable fallback and rerouting logic

---

## 🛠️ Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/your-username/distributed_troubleshooter.git
cd distributed_troubleshooter
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run with Docker Compose
```bash
docker-compose up --build
```

### 4. Access via browser
- `http://localhost:8000` → North
- `http://localhost:8001` → South
- `http://localhost:8002` → East
- `http://localhost:8003` → West

---

## 🌐 Frontend Dashboard Links

| Role       | File                   | Description                          |
|------------|------------------------|--------------------------------------|
| User       | `user_dashboard.html`  | Submit & track issues, chat, rate    |
| Expert     | `expert_dashboard.html`| Resolve issues, chat, mark complete  |
| Admin      | `admin_dashboard.html` | Verify experts, view stats           |
| General    | `index.html`           | Login / Signup                       |

---

## 💡 Future Enhancements

- ⚡ WebSocket-based real-time messaging
- 📩 Email & SMS notification system
- 🧠 AI-based expert ranking (RL + LLM)
- 🌐 Multilingual issue reporting
- ⏳ Trust decay for inactive experts

---
