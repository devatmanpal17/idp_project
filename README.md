# CogniVue Insight — AI-Powered MOOC Mastery & Retention Platform

A production-grade, 3-tier intelligent learning analytics and assessment engine. CogniVue tracks learner interactions across MOOC platforms (Udemy, Coursera, edX), quantifies multi-signal topic mastery, builds Ebbinghaus-based spaced repetition schedules, and generates adaptive RAG-grounded assessments with live telemetry.

---

## 3-Tier Architecture Overview

The repository is segregated into three dedicated tiers:

```
cognivue-insight/
├── ml/            # Machine Learning & AI Core (RAG Vector Index, LLMs, Calibration)
├── backend/       # FastAPI REST API Backend Server
└── frontend/      # React 19 + TanStack Router + Tailwind CSS UI Application
```

---

### 1. `ml/` — Machine Learning & RAG Engine
- **`knowledge_base.py`**: Lecture transcript corpus across Data Structures, ML, React, and Databases.
- **`rag_engine.py`**: TF-IDF vector embeddings, cosine similarity search, and context chunk retrieval.
- **`llm_service.py`**: Multi-provider AI generation pipeline (Google Gemini 1.5/2.0 Flash, OpenAI GPT-4o-mini, and local intelligent generator).
- **`calibration.py`**: Learner signal difficulty calibration and Bayesian mastery updating.

### 2. `backend/` — FastAPI REST API Layer
- **`app.py`**: FastAPI application factory and CORS configuration.
- **`models.py`**: Pydantic request/response schemas.
- **`routes/`**:
  - `health.py`: Status, chunk index metrics, and active AI engine health checks (`/api/health`).
  - `rag.py`: RAG vector retrieval, quiz generation, grading, and transcript ingestion (`/api/rag/*`).
  - `recommendations.py`: Smart spaced repetition study recommendations (`/api/recommendations/smart`).
  - `settings.py`: Runtime AI provider/key configuration (`/api/settings/ai-config`).
- **`run.py`**: Direct executable runner.

### 3. `frontend/` — Web Application
- **`src/routes/`**: Complete 8-screen dashboard system:
  1. **Overview Dashboard**: High-level mastery, weak spot alerts, AI drill launch modal, live activity feed.
  2. **Courses Directory**: Multi-platform enrollment tracking (Udemy, Coursera, edX).
  3. **Course Deep Dive**: Section-by-section breakdown with interactive quiz generator.
  4. **Mastery Analytics**: Interactive signal weight sliders (Quiz, Time, Revisit) with instant recalculation.
  5. **Quizzes & Diagnostic Assessments**: Question-by-question review with pedagogical rationale citations.
  6. **Adaptive Study Plan**: Ebbinghaus retention decay curves and scheduled review calendar.
  7. **Smart Recommendations**: Impact-ranked corrective study blocks.
  8. **Chrome Extension Overlay Simulator**: Live simulated video player overlay with real-time transcript streaming.
  9. **Settings & AI Configuration**: Runtime switching between Gemini, OpenAI, and Local RAG.

---

## Quickstart Guide

### Prerequisites
- Node.js 18+ & npm
- Python 3.10+

### 1. Start the ML/Backend API Server
```bash
# Install Python dependencies
pip install -r backend/requirements.txt

# Start FastAPI server on port 8000
python -m uvicorn backend.app:app --port 8000 --reload
# or: python -m backend.run
```

### 2. Start the Frontend Development Server
```bash
cd frontend
npm install
npm run dev
```

The frontend will start at **`http://localhost:8080`** and automatically proxy `/api` requests to the Python backend at `http://127.0.0.1:8000`.

---

## Verification & Testing

```bash
# Typecheck frontend
cd frontend && npx tsc --noEmit

# Build production bundle
cd frontend && npm run build

# Test Backend & ML
python -c "import ml, backend; print('ML and Backend verified successfully!')"
```
