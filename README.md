# 🌤️ Niva — Intelligent Thermal Companion & Retail Analytics

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React_18-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white)](https://vitejs.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=flat&logo=tailwind-css&logoColor=white)](https://tailwindcss.com)
[![PWA Ready](https://img.shields.io/badge/PWA-Ready-orange?style=flat&logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Niva** is a mobile-first, privacy-conscious thermal layering assistant and B2B retail intelligence platform. Powered by hyper-local weather telemetry, dynamic thermal modeling, and edge AI, Niva translates raw atmospheric metrics into intuitive dressing recommendations, multi-day luggage planning, and demographic clothing demand forecasts.

---

## 🌟 Key Features

### 1. Adaptive Thermal Engine
* **Biometric Calibration ($\Delta T$):** Learns and calibrates against individual thermal sensitivities and personal comfort offsets.
* **Diurnal Thermal Dynamics:** Automatically detects daily temperature swings ($\ge 6^\circ\text{C}$) between morning (08:00), afternoon (14:00), and evening (20:00) to recommend packable or removable mid-layers (cardigans, zip fleeces).
* **Weather-Responsive Layering:** Seamlessly factors in wind chill, humidity, precipitation probability, and UV index.

### 2. Multi-Day Travel & Smart Packing Planner *(Authenticated)*
* **Weather Spectrum Analysis:** Scans target destination forecasts for up to 14 days, identifying temperature extremes and precipitation windows.
* **Probabilistic Rain & Gear Advice:** Recommends compact travel umbrellas for low-to-moderate rain risks (20%–39%) and full waterproof shells for severe precipitation ($\ge 40\%$).
* **Unquantified Practical Checklist:** Provides categorized clothing checklists (Base, Mid, Outer, Accessories) without rigid quantity enforcement.
* **Export & Sharing:** Save trips to user profiles, check off items in real-time, share summaries directly via WhatsApp, or copy formatted markdown to clipboard.

### 3. Voice & Text Companion ("Ask Niva")
* **Interactive AI Dialog:** Ask weather- or outfit-related questions via speech (Web Speech API) or direct text input.
* **Edge-TTS Audio Synthesis:** Conversational audio feedback generated in real time:
  * Turkish (`tr-TR-EmelNeural`)
  * Swiss High German (`de-CH-JanNeural`)
  * English (`en-US-ChristopherNeural`)

### 4. B2B Retail Trends & Demographics Workspace
* **Gender-Segmented Analytics:** Filter garment demand and historical wearing trends by demographic groups (`Men`, `Women`, `Other`).
* **Forecasted Inventory Demand:** Insights into anticipated outer-layer surges based on upcoming 7-day regional weather trends.
* **Role-Based Access Control:** Tiered access across `User`, `Partner`, and `Admin` personas with CSV trend exporting.

### 5. Mobile-First PWA Experience & Accessibility
* **Installable PWA:** Full standalone mobile experience with offline asset caching and zero browser chrome.
* **Compact Ergonomics:** Apple Weather-style dense 7-day forecast list, responsive drawer menus, and touch targets $\ge 48\text{px}$.
* **Senior Mode:** One-tap toggle for high-contrast outlines, enlarged typography, and simplified navigation.

---

## 🛠️ Architecture & Tech Stack

```
niva/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── api/v1/           # API Routers (auth, recommendations, travel, analytics, assistant)
│   │   ├── core/             # Security, JWT, Database session & settings
│   │   ├── models/           # SQLAlchemy Data Models
│   │   ├── schemas/          # Pydantic Schemas
│   │   └── services/         # Thermal Engine, Travel Engine, Weather & TTS Services
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 # React 18 + Vite SPA
│   ├── src/
│   │   ├── components/       # WeatherCard, SevenDayForecast, TravelView, AdminWorkspace
│   │   ├── contexts/         # Auth, Language (i18n), and Accessibility Contexts
│   │   ├── i18n/             # EN, DE-CH, and TR Translation Dictionaries
│   │   └── services/         # API clients (Axios) & PWA Service Worker
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml        # Multi-container orchestration
└── .env.example              # Environment blueprint
```

* **Backend:** Python 3.11+, FastAPI, SQLAlchemy, SQLite (Development) / PostgreSQL (Production), Edge-TTS.
* **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons.
* **Weather & Geo:** Open-Meteo Free Weather API & Geocoding.
* **Decision Engine:** Cloudflare Workers AI / Local Fallback Rules.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.11+
* Node.js 18+ & npm / pnpm
* Docker & Docker Compose *(optional, for containerized run)*

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/niva-thermal-assistant.git
cd niva-thermal-assistant
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv

# Linux / macOS:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

pip install -r requirements.txt
cp ../.env.example .env
```

Start the FastAPI development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API documentation will be available at `http://localhost:8000/docs`.

### 3. Frontend Setup
```bash
cd ../frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## ⚙️ Environment Configuration (`.env`)

Copy `.env.example` to `.env` and fill in your credentials:

```env
# Application
PROJECT_NAME="Niva Thermal Companion"
ENVIRONMENT="development"
SECRET_KEY="your-super-secret-jwt-key"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Database
DATABASE_URL="sqlite:///./niva.db"

# Cloudflare Workers AI (Optional, fallbacks are included)
CLOUDFLARE_ACCOUNT_ID=""
CLOUDFLARE_API_TOKEN=""

# CORS Origins
BACKEND_CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]
```

---

## 🐳 Docker Deployment

To launch the complete stack using Docker Compose:

```bash
docker compose up -d --build
```

* **Frontend:** `http://localhost:80`
* **Backend API:** `http://localhost:8000`

---

## 🌐 Localization (i18n)

Niva ships with native, out-of-the-box support for three locales:
* **English (`en`)** — Default international locale.
* **Swiss High German (`de`)** — Standard Swiss German orthography (uses `ss` instead of `ß`).
* **Turkish (`tr`)** — Tailored localized terminology and phrasing.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
