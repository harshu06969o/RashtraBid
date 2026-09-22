# RashtraBid 🇮🇳

**AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement**

*Smart India Hackathon 2026 | Problem Statement: 26100 | Ministry of Petroleum & Natural Gas (CPCL)*

---

## 📑 Overview

Government procurement through the Government e-Marketplace (GeM) involves rigorous verification of statutory, regulatory, and eligibility requirements. Procurement officers manually validate documents like Udyam/MSME registration, GSTIN, PAN, Make in India (MII) content, EPFO compliance, and technical criteria. This document-intensive process leads to significant manual effort, extended evaluation cycles, and potential human error.

**RashtraBid** solves this by providing a unified, AI-driven automation pipeline. It ingests Tender RFPs, extracts structured compliance rules, and automatically cross-verifies bidder submissions using AI models (Gemini) and integrated registry checks, driving evaluation times down by 80%.

### 🎯 Expected Impact
- **60-80% Reduction in Verification Effort**: Zero manual document checking.
- **Faster Tender Evaluation & Award**: L1 generation in minutes, not weeks.
- **Improved Compliance & Transparency**: SHA-256 tamper-evident audit logs.
- **Reduced Human Errors**: Automated data extraction and classification.
- **Better Bidder Screening**: Instant anomaly detection.
- **Complete Auditability**: Step-by-step traceability of every automated and manual decision.

---

## 🚀 Key Features

1. **AI Tender Compiler**: Upload an RFP (PDF), and our engine extracts financial turnover requirements, MII %, statutory registrations, and technical specifications into discrete, trackable rules.
2. **Automated Bidder Verification**: Bidders upload documents; the platform uses Gemini AI to extract entities and verify them against tender rules.
3. **Corrigendum Analyzer**: Upload tender amendments (Corrigenda). The AI detects what rules changed, maps them, and flags previously compliant bids that need re-verification.
4. **Automated L1 Financial Ranking**: Secure financial envelopes are processed, prices extracted, and a comprehensive L1 ranking board is generated automatically.
5. **Government-Grade UI**: Built with an AICTE-portal inspired design—fluid, accessible (WCAG 2.1 AA), fully responsive, dark-mode ready, and available in 8 Indian languages.
6. **Officer Override & Audit Trail**: Procurement officers retain final control. Overrides are captured in a cryptographically secure audit trail.

---

## 🏗️ Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                           │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │    Web UI    │     │  Mobile App  │     │  API Client  │     │
│  │ (React/Vite) │     │              │     │              │     │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘     │
└─────────┼────────────────────┼────────────────────┼─────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API GATEWAY                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 Express Gateway (Node.js)               │    │
│  │  • Rate Limiting  • CORS Policy  • Route Forwarding     │    │
│  └─────────────────────────┬───────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────┘
                             │
          ┌──────────────────┴──────────────────┐
          ▼                                     ▼
┌─────────────────┐                   ┌─────────────────┐
│     BACKEND     │                   │     STORAGE     │
│  FastAPI Core   │                   │                 │
│ • JWT Auth      │                   │ • MongoDB       │
│ • RBAC Control  │                   │ • Cloudinary    │
│ • Pydantic      │                   │ • Ephemeral Disk│
└────────┬────────┘                   └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                          AI PIPELINE                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 Gemini AI Engine (Flash)                │    │
│  │                                                         │    │
│  │ Document ──► OCR ──► Extractor ──► Classifier ──► Score │    │
│  └─────────────────────────┬───────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       REGISTRY ADAPTERS                         │
│  ┌──────┐  ┌───────┐  ┌─────┐  ┌──────┐  ┌─────┐  ┌───────┐     │
│  │ GSTN │  │ Udyam │  │ PAN │  │ EPFO │  │ MCA │  │ GeM   │     │
│  └──────┘  └───────┘  └─────┘  └──────┘  └─────┘  └───────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```text
RashtraBid/
├── api-gateway/               # Express.js Gateway (Port 3000)
│   ├── index.js               # Route proxy and rate limiting
│   └── package.json
├── backend/                   # FastAPI Server (Port 8001)
│   ├── app/
│   │   ├── main.py            # Application entry point
│   │   ├── core/              # Config, DB connection, JWT auth
│   │   ├── models/            # Pydantic schemas and types
│   │   ├── pipeline/          # AI processing logic (Gemini)
│   │   │   ├── tender_compiler.py
│   │   │   └── corrigendum_analyzer.py
│   │   └── routers/           # API Endpoints
│   │       ├── auth.py        # Login, registration, RBAC
│   │       ├── tenders.py     # Tender & Rules CRUD
│   │       ├── bids.py        # Bid evaluations & Officer actions
│   │       ├── corrigendum.py # Corrigendum processing
│   │       └── financial.py   # L1 ranking
│   ├── requirements.txt
│   └── .env                   # Backend environment variables
├── frontend/                  # React Frontend (Vite)
│   ├── src/
│   │   ├── api/               # API client (Axios)
│   │   ├── components/        # Reusable UI components
│   │   ├── i18n/              # Translations (8 languages)
│   │   ├── pages/             # Route views (Landing, Dashboard, etc.)
│   │   └── store/             # Redux state management
│   ├── package.json
│   └── vite.config.js
└── README.md
```

---

## 🛠️ Technology Stack

| Layer | Technology | Why |
| :--- | :--- | :--- |
| **API Gateway** | Express.js | Lightweight proxy, rate limiting |
| **Backend API** | FastAPI (Python) | Async, extremely fast, auto-docs |
| **Database** | MongoDB (Motor) | Flexible document schema for RFPs |
| **Auth** | JWT + bcrypt | Stateless, secure RBAC |
| **AI Engine** | Gemini 1.5 Flash | High-speed structured data extraction |
| **File Storage** | Cloudinary / Local | Media persistence and fast delivery |
| **Frontend** | React (Vite) | Component-based, lightning fast HMR |
| **State Mgt.** | Redux Toolkit | Predictable state for complex workflows |
| **Styling** | Vanilla CSS + Inline | Zero heavy dependencies, custom tokens |

---

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- Python 3.10+
- MongoDB instance (Atlas or Local)
- Google Gemini API Key
- Cloudinary Credentials

### 1. Environment Setup

Configure the `.env` files for the backend and API gateway based on the `.env.example` equivalents.

**`backend/.env`**
```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=bharatbid
JWT_SECRET=supersecret_key
GEMINI_API_KEY=your_gemini_api_key
CLOUDINARY_URL=cloudinary://your_url
```

### 2. Start All Services

You can run the stack simultaneously in different terminal windows:

**API Gateway (Port 3000):**
```bash
cd api-gateway
npm install
npm run dev
```

**Backend (Port 8001):**
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
```

**Frontend (Port 5173):**
```bash
cd frontend
npm install
npm run dev
```

### 3. Access the Portal

Open your browser and navigate to: **`http://localhost:5173`**

- **Procurement Officer Login**: `officer@gem.gov.in` / `officer123`
- **Bidder Login**: `bidder@company.com` / `bidder123`

---

## 📡 API Endpoints (Core)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/auth/token` | Get JWT token (Login) |
| `POST` | `/api/v1/auth/register` | Register new Bidder |
| `POST` | `/api/v1/tenders/upload` | Upload & Compile RFP (AI) |
| `GET` | `/api/v1/tenders` | List active Tenders |
| `POST` | `/api/v1/bids/{id}/documents` | Upload bidder compliance doc |
| `POST` | `/api/v1/bids/{id}/officer-action`| Officer Manual Override |
| `POST` | `/api/v1/corrigendum/upload` | Process Tender Amendment (AI) |
| `GET` | `/api/v1/financial/{id}/rank` | Generate L1 Financial Ranking |

---

## 🛡️ Security & Compliance

- **GIGW 3.0 & WCAG 2.1 AA**: The user interface is fully accessible, compliant with Indian Government guidelines.
- **AES-256 & TLS 1.3**: Data in transit and at rest is secured.
- **SHA-256 Audit Chain**: Every rule change, automated validation, and officer override is logged with a cryptographic hash, ensuring tamper-evident tracking.
- **RBAC**: Strict role-based access control separating `BIDDER` and `PROCUREMENT_OFFICER` scopes.

---

## 📄 License
Proprietary — Built exclusively for **Smart India Hackathon 2026** (Ministry of Petroleum & Natural Gas). All rights reserved.
