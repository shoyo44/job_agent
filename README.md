# Job Agent

Job Agent is a full-stack automation platform for discovering, scoring, and submitting job applications with a controllable approval flow.

It combines:

- a FastAPI backend for orchestration, auth, diagnostics, and APIs
- a React + Vite frontend for onboarding and live run monitoring
- Playwright for LinkedIn scraping and Easy Apply automation
- Cloudflare Workers AI for parsing, scoring, and generation tasks
- Firebase Authentication for user identity and protected endpoints
- MongoDB (preferred) or Excel (fallback) for application tracking
- optional Telegram notifications for final run summaries

## Demonstration Video Link:
https://drive.google.com/file/d/1hxPYVRZK5nlGQREKP5rAn-IkGcaf4rNy/view?usp=sharing

## Who This Is For

This project is useful if you want to:

- automate job discovery and ranking from a natural-language goal
- run a browser-based pipeline with observable progress and artifacts
- keep persistent records of outcomes and statuses
- separate dry-run validation from real submissions

## High-Level Capabilities

The system supports two execution styles:

1. Web mode (recommended)
2. CLI mode (direct backend execution)

In both modes, the same core pipeline is used:

1. Parse user goal and constraints
2. Generate search plans
3. Scrape jobs from LinkedIn
4. Score jobs against profile/resume
5. Select finalists
6. Generate tailored cover letters
7. Attempt submission
8. Store outcomes and return run summary

Current default tuning:

- score top 5 jobs
- keep up to 3 critic-approved finalists
- submit finalists in order
- stop after the first successful application

## Clean System Architecture

### Logical architecture (component view)

```text
+-----------------------+         +--------------------------+
|   React Frontend      |         |   External Services      |
|  (Vite + TypeScript)  |         |--------------------------|
|-----------------------|         | Firebase Auth            |
| - Google sign-in      |<------->| Cloudflare Workers AI    |
| - Onboarding          |         | LinkedIn                 |
| - Run dashboard       |         | MongoDB (optional)       |
| - Tracker/history     |         | Telegram (optional)      |
+-----------+-----------+         +------------+-------------+
            |                                   ^
            | HTTPS (Bearer token)              |
            v                                   |
+-----------+-----------------------------------+-------------+
|                    FastAPI Backend                          |
|-------------------------------------------------------------|
| API Layer: auth, run, tracker, diagnostics, docs summary    |
| Service Layer: run orchestration + async run state          |
| Agent Layer: manager, planner, critic, cover-letter, submit |
| Tool Layer: scraping, resume parsing, tracking, telegram    |
+-----------+-------------------------------+-----------------+
            |                               |
            v                               v
+-----------+-----------+       +-----------+----------------+
| Runtime Artifacts     |       | Browser Runtime           |
|-----------------------|       |---------------------------|
| backend/data/*.jsonl  |       | Playwright profile per run|
| backend/data/*.xlsx   |       | shared across scrape/apply|
| backend/data/debug/*  |       | backend/data/runtime_*    |
+-----------------------+       +---------------------------+
```

### Runtime sequence (web mode)

```text
Frontend
  -> Firebase sign-in
  -> POST /api/v1/auth/firebase-login
  -> POST /api/v1/run/async
  -> FastAPI service creates run_id + state
  -> ManagerAgent parses goal + constraints
  -> PlannerAgent builds queries + scores jobs
  -> LinkedIn scraper collects candidate jobs
  -> CriticAgent keeps best finalists
  -> CoverLetterAgent generates tailored content
  -> SubmissionAgent executes Easy Apply attempts
  -> TrackerAgent writes statuses/results
  -> GET /api/v1/run/{run_id} polling
  -> UI renders progress + final report
```

### Layered responsibilities

- Presentation layer (frontend)
- collects credentials and preferences
- starts runs and polls progress
- renders step-level output, run summary, and tracker history

- API layer (FastAPI)
- validates request schemas
- verifies Firebase token for protected endpoints
- provides health/startup diagnostics
- exposes run/tracker/telegram interfaces

- Orchestration layer (service + agents)
- enforces pipeline order and stop conditions
- executes dry-run or real-run strategy
- passes structured outputs between agents

- Integration/tool layer
- Playwright browser automation and session persistence
- AI model calls for scoring and generation
- tracker persistence (MongoDB/Excel)
- optional Telegram final notification

### Reliability strategy

- Shared run-scoped browser profile for scraper -> submission handoff
- Async run state endpoint for frontend polling and recovery
- MongoDB-first tracking with Excel fallback path
- Telegram failures do not fail the core pipeline result
- Diagnostics endpoint for startup dependency visibility

## Repository Layout

```text
Job Agent/
  backend/
    agent/
      manager_agent.py
      planner_agent.py
      critic_agent.py
      submission_agent.py
      tracker_agent.py
      submission/
    api/
      app.py
      service.py
      models.py
    tools/
      cover_letter.py
      resume_tools.py
      job_tools.py
      submission_tools.py
      tracking_tools.py
      telegram_bot.py
      agent_jsonl.py
    web_scrapping/
      linkedin_playwrite.py
    tests/
    data/
    config.py
    main.py
    api_server.py
    requirements.txt
    serviceAccountKey.json
  frontend/
    src/
      components/
      config/
      hooks/
      services/
      types/
      utils/
    package.json
  data/
  README.md
  SETUP_GUIDE.md
  COMMANDS.md
  requirements.txt
```

## Key Files By Concern

### Frontend experience

- [ConsoleDashboard.tsx](/d:/Projects/Job%20Agent/frontend/src/components/ConsoleDashboard.tsx)
- [PipelineConfig.tsx](/d:/Projects/Job%20Agent/frontend/src/components/PipelineConfig.tsx)
- [ExecutionOutput.tsx](/d:/Projects/Job%20Agent/frontend/src/components/ExecutionOutput.tsx)
- [OverviewPanel.tsx](/d:/Projects/Job%20Agent/frontend/src/components/OverviewPanel.tsx)
- [api.ts](/d:/Projects/Job%20Agent/frontend/src/services/api.ts)
- [firebase.ts](/d:/Projects/Job%20Agent/frontend/src/config/firebase.ts)

### Backend API and orchestration

- [app.py](/d:/Projects/Job%20Agent/backend/api/app.py)
- [service.py](/d:/Projects/Job%20Agent/backend/api/service.py)
- [models.py](/d:/Projects/Job%20Agent/backend/api/models.py)

### Automation and pipeline runtime

- [linkedin_playwrite.py](/d:/Projects/Job%20Agent/backend/web_scrapping/linkedin_playwrite.py)
- [submission_agent.py](/d:/Projects/Job%20Agent/backend/agent/submission_agent.py)
- [submission_tools.py](/d:/Projects/Job%20Agent/backend/tools/submission_tools.py)

### Tracking and notifications

- [tracker_agent.py](/d:/Projects/Job%20Agent/backend/agent/tracker_agent.py)
- [tracking_tools.py](/d:/Projects/Job%20Agent/backend/tools/tracking_tools.py)
- [telegram_bot.py](/d:/Projects/Job%20Agent/backend/tools/telegram_bot.py)

## Authentication Model

1. User signs in via Firebase Google provider on frontend.
2. Frontend receives Firebase ID token.
3. Frontend sends token as `Authorization: Bearer <token>`.
4. Backend verifies token using Firebase Admin SDK and `serviceAccountKey.json`.
5. Protected endpoints execute only for valid identity.

## Pipeline Deep-Dive

### ManagerAgent

- parses job goal into role, location, work-mode, and constraints
- normalizes profile preferences for downstream steps

### PlannerAgent

- creates search plans/queries
- scores scraped jobs against resume and profile signal
- keeps top candidates for critic review

### CriticAgent

- applies a stricter selection pass
- outputs a small finalist set for submission

### CoverLetterAgent

- generates customized letter text from resume + job context

### SubmissionAgent

- performs Easy Apply attempt flow where supported
- attempts finalist jobs in sequence until success condition is met

### TrackerAgent

- records each job attempt and status transition
- powers history/stats endpoints for dashboard and audits

## Data and Runtime Artifacts

Common outputs under backend runtime:

- `backend/data/agent.log`
- `backend/data/list.xlsx`
- `backend/data/agent_context.jsonl`
- `backend/data/agent_context_<run_id>.jsonl`
- `backend/data/runtime_browser_profiles/`
- `backend/data/runtime_resumes/`
- `backend/data/debug/`

Use these artifacts when investigating scoring decisions, submission behavior, or failed runs.

## API Overview

### Diagnostics

- `GET /api/v1/health`
- `GET /api/v1/startup`
- `GET /api/v1/config`

### Auth

- `POST /api/v1/auth/firebase-login`
- `GET /api/v1/me`

### Pipeline

- `POST /api/v1/run`
- `POST /api/v1/run/async`
- `GET /api/v1/run/{run_id}`

### Tracker

- `GET /api/v1/tracker/stats`
- `GET /api/v1/tracker/history`
- `POST /api/v1/tracker/update-status`

### Telegram

- `GET /api/v1/telegram/status`
- `POST /api/v1/telegram/test`

### Frontend support

- `GET /api/v1/features`
- `GET /api/v1/docs-summary`

## Requirements

### Required

- Python 3.11+
- Node.js 20+
- npm 10+
- Firebase project (Google sign-in)
- LinkedIn account

### Optional but recommended

- MongoDB Atlas or local MongoDB
- Telegram bot token and chat ID

Dependency files:

- [requirements.txt](/d:/Projects/Job%20Agent/requirements.txt)
- [backend/requirements.txt](/d:/Projects/Job%20Agent/backend/requirements.txt)
- [frontend/package.json](/d:/Projects/Job%20Agent/frontend/package.json)

## Quick Start

### 1) Environment setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cd frontend
npm install
cd ..
```

### 2) Backend

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### 3) Frontend

In a new terminal:

```powershell
cd frontend
npm run dev
```

Then open `http://127.0.0.1:5173`.

## Setup and Operations Docs

- Detailed setup and environment walkthrough: [SETUP_GUIDE.md](/d:/Projects/Job%20Agent/SETUP_GUIDE.md)
- Command cookbook for daily use: [COMMANDS.md](/d:/Projects/Job%20Agent/COMMANDS.md)

## Testing

Backend tests:

```powershell
cd backend
pytest -q
```

Targeted backend tests:

```powershell
cd backend
pytest tests/test_manager_agent.py -q
pytest tests/test_planner_agent.py -q
pytest tests/test_tracker_agent.py -q
pytest tests/test_integration_dry_run.py -q
```

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
npx tsc -b
```

## Troubleshooting

### `Failed to fetch` in frontend

Likely causes:

- backend not running
- wrong `VITE_API_BASE_URL`
- CORS origin mismatch

### `/api/v1/startup` reports Mongo `ok=False`

Check:

- `MONGODB_URI`
- database credentials
- network allowlist (Atlas)
- cluster availability

### Firebase login fails

Check:

- frontend Firebase env vars
- backend `serviceAccountKey.json`
- local system clock skew

### LinkedIn opens feed instead of job page

This is usually a session restoration issue. Confirm logs show a recovered `/jobs/view/...` URL before submission steps continue.

### Telegram not sending automatically

Most commonly:

- `TELEGRAM_ENABLED=false`

## Security Notes

- never commit `backend/.env`
- never commit real `frontend/.env`
- treat `backend/serviceAccountKey.json` as sensitive
- do not expose LinkedIn credentials
- rotate leaked keys/tokens immediately

## Suggested Development Workflow

1. Start backend and confirm `/api/v1/startup`.
2. Start frontend and sign in with Google.
3. Run dry-run first (`DRY_RUN=true`).
4. Inspect logs, scoring, and finalists.
5. Enable live submission after dry-run confidence.
6. Review tracker history and exported artifacts.
