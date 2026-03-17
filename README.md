# Job Agent

Job Agent is a full-stack job application automation system with:

- a FastAPI backend for orchestration, tracking, diagnostics, and auth
- a React + Vite frontend for onboarding, live pipeline monitoring, and history
- Playwright-based LinkedIn scraping and Easy Apply submission
- Cloudflare Workers AI for goal parsing, scoring, critic review, and cover-letter generation
- Firebase Authentication for protected API access
- MongoDB or Excel-based application tracking
- optional Telegram notifications for final run summaries

The project can be used in two ways:

- `python main.py` for a direct CLI-driven backend run
- `uvicorn api.app:app --reload` + the frontend for an authenticated web workflow

## What The Project Does

At a high level, the system:

1. understands a job-search goal
2. builds search queries
3. scrapes matching LinkedIn jobs
4. scores the jobs against the resume/profile
5. keeps the top scored jobs
6. lets the critic choose the strongest finalists
7. generates tailored cover letters
8. attempts LinkedIn submission until the configured success target is met
9. stores application results in MongoDB or Excel
10. optionally sends a final Telegram summary

The current web pipeline is tuned to:

- score the top 5 jobs
- keep up to 3 critic-approved finalists
- try submission in order
- stop after 1 successful application

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
      models.py
      service.py
    tools/
      cover_letter.py
      resume_tools.py
      job_tools.py
      submission_tools.py
      telegram_bot.py
      tracking_tools.py
      agent_jsonl.py
    web_scrapping/
      linkedin_playwrite.py
    data/
    tests/
    config.py
    main.py
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
    public/
    package.json
  data/
  requirements.txt
```

## Architecture

### 1. Frontend

The frontend is a Vite + React + TypeScript application.

Main responsibilities:

- Firebase Google sign-in
- collecting LinkedIn credentials and resume upload during onboarding
- starting async pipeline runs through FastAPI
- polling run status through `/api/v1/run/{run_id}`
- showing live pipeline progress, final results, tracker history, and diagnostics

Important frontend files:

- [ConsoleDashboard.tsx](/d:/Projects/Job%20Agent/frontend/src/components/ConsoleDashboard.tsx)
- [PipelineConfig.tsx](/d:/Projects/Job%20Agent/frontend/src/components/PipelineConfig.tsx)
- [ExecutionOutput.tsx](/d:/Projects/Job%20Agent/frontend/src/components/ExecutionOutput.tsx)
- [OverviewPanel.tsx](/d:/Projects/Job%20Agent/frontend/src/components/OverviewPanel.tsx)
- [api.ts](/d:/Projects/Job%20Agent/frontend/src/services/api.ts)
- [firebase.ts](/d:/Projects/Job%20Agent/frontend/src/config/firebase.ts)

### 2. FastAPI backend

The FastAPI app exposes:

- auth endpoints
- diagnostics endpoints
- pipeline run endpoints
- tracker endpoints
- Telegram inspection/test endpoints

Main backend API files:

- [app.py](/d:/Projects/Job%20Agent/backend/api/app.py)
- [service.py](/d:/Projects/Job%20Agent/backend/api/service.py)
- [models.py](/d:/Projects/Job%20Agent/backend/api/models.py)

Important behavior:

- frontend users authenticate with Firebase in the browser
- the frontend sends the Firebase ID token to FastAPI
- FastAPI verifies that token using Firebase Admin SDK
- protected endpoints require a valid Bearer token

### 3. Agent pipeline

The backend orchestrates several agents:

- `ManagerAgent`
  - parses the job goal into roles, locations, work mode, and run preferences
- `PlannerAgent`
  - builds search queries and scores scraped jobs
- `CriticAgent`
  - chooses the strongest finalists
- `CoverLetterAgent`
  - generates tailored cover letters from the resume and job context
- `SubmissionAgent`
  - drives LinkedIn Easy Apply or best-effort external apply flows
- `TrackerAgent`
  - stores and summarizes outcomes

### 4. Scraping and submission runtime

LinkedIn automation uses Playwright persistent browser contexts.

Important files:

- [linkedin_playwrite.py](/d:/Projects/Job%20Agent/backend/web_scrapping/linkedin_playwrite.py)
- [submission_agent.py](/d:/Projects/Job%20Agent/backend/agent/submission_agent.py)
- [submission_tools.py](/d:/Projects/Job%20Agent/backend/tools/submission_tools.py)

For FastAPI-triggered runs, the scraper and submission agent share a run-scoped browser profile under:

- `backend/data/runtime_browser_profiles/<run_id>`

That shared profile is important because it lets the logged-in LinkedIn session survive the handoff from scraping to submission.

### 5. Tracking layer

Tracking supports two backends:

- MongoDB
- Excel fallback

Important file:

- [tracker_agent.py](/d:/Projects/Job%20Agent/backend/agent/tracker_agent.py)

MongoDB is preferred when `MONGODB_URI` is configured and reachable.
If MongoDB is unavailable, the tracker can fall back to the Excel file defined by `EXCEL_FILE_PATH`.

### 6. Telegram integration

Telegram is optional and currently designed to send only final run summaries.

Important file:

- [telegram_bot.py](/d:/Projects/Job%20Agent/backend/tools/telegram_bot.py)

The backend is intentionally hardened so Telegram delivery failure does not break pipeline results returned to the frontend or CLI.

## Request Flow

### Web flow

```text
React frontend
  -> Firebase Google sign-in
  -> POST /api/v1/auth/firebase-login
  -> POST /api/v1/run/async
  -> FastAPI execute_pipeline()
  -> ManagerAgent
  -> PlannerAgent
  -> LinkedIn scraper
  -> CriticAgent
  -> CoverLetterAgent
  -> SubmissionAgent
  -> TrackerAgent
  -> GET /api/v1/run/{run_id} polling
  -> frontend workflow + results view
```

### CLI flow

```text
python main.py
  -> prompt user
  -> ManagerAgent
  -> PlannerAgent
  -> LinkedIn scraper
  -> CriticAgent
  -> CoverLetterAgent
  -> SubmissionAgent
  -> TrackerAgent
  -> console summary
```

## Requirements

### System requirements

- Windows, macOS, or Linux
- Python 3.11+ recommended
- Node.js 20+ recommended
- npm 10+ recommended
- Google Firebase project for frontend sign-in
- LinkedIn account for scraping/submission

Optional but recommended:

- MongoDB Atlas or local MongoDB
- Telegram bot token and chat ID

### Python dependencies

The backend dependency list lives in:

- [backend/requirements.txt](/d:/Projects/Job%20Agent/backend/requirements.txt)

A top-level convenience file is also provided:

- [requirements.txt](/d:/Projects/Job%20Agent/requirements.txt)

### Frontend dependencies

Frontend dependencies are defined in:

- [package.json](/d:/Projects/Job%20Agent/frontend/package.json)

## Setup Guide

### 1. Clone the repository

```powershell
git clone <your-repo-url>
cd "Job Agent"
```

### 2. Create and activate a Python virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

From the project root:

```powershell
pip install -r requirements.txt
```

Or directly from the backend folder:

```powershell
cd backend
pip install -r requirements.txt
```

### 4. Install Playwright Chromium

This is required for scraping and submission.

```powershell
python -m playwright install chromium
```

If Playwright browser startup fails on a fresh machine, run:

```powershell
python -m playwright install
```

### 5. Install frontend dependencies

```powershell
cd frontend
npm install
```

### 6. Configure backend environment

Create or update:

- `backend/.env`

The backend reads configuration from [config.py](/d:/Projects/Job%20Agent/backend/config.py).

Important environment variables:

#### Cloudflare Workers AI

```env
CF_ACCOUNT_ID=
CF_API_TOKEN=
CF_MODEL=@cf/meta/llama-3.1-8b-instruct
```

#### LinkedIn credentials

```env
LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=
```

These can also be supplied per-run from the frontend.

#### User profile

```env
USER_NAME=
USER_EMAIL=
USER_PHONE=
USER_LOCATION=Bangalore
USER_RESUME_PATH=data/resume.pdf
USER_TARGET_ROLES=AI Engineer,Machine Learning Engineer
USER_TARGET_LOCATIONS=Bangalore,Remote
USER_MIN_SALARY=0
USER_WORK_MODE=any
USER_YEARS_EXPERIENCE=2
USER_LINKEDIN_URL=
USER_PORTFOLIO_URL=
USER_WORK_AUTHORIZED=yes
USER_REQUIRES_SPONSORSHIP=no
```

#### Run defaults

```env
MIN_CONFIDENCE_SCORE=65
MAX_APPLICATIONS_PER_RUN=10
DRY_RUN=true
```

#### Tracking

```env
EXCEL_FILE_PATH=data/list.xlsx
LOG_FILE_PATH=data/agent.log
MONGODB_URI=
MONGODB_DB=job_agent
MONGODB_COLLECTION=applications
```

#### Telegram

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ENABLED=false
TELEGRAM_POLL_TIMEOUT=30
```

#### Browser automation

```env
CHROMIUM_PATH=
HEADLESS=false
HUMAN_DELAY_MS=1500
USE_TEMP_BROWSER_PROFILE=false
RUNTIME_BROWSER_PROFILE_DIR=
```

### 7. Configure Firebase Admin for backend auth

Place the Firebase Admin service account JSON at:

- `backend/serviceAccountKey.json`

The backend uses this file for token verification.

### 8. Configure frontend environment

Create:

- `frontend/.env`

Recommended values:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
VITE_FIREBASE_MEASUREMENT_ID=
```

## Running The Project

### Option A: Full web app

Start the backend:

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Start the frontend in another terminal:

```powershell
cd frontend
npm run dev
```

Open:

- `http://127.0.0.1:5173`

### Option B: CLI-only backend run

```powershell
cd backend
python main.py
```

### Option C: Backend helper entrypoint

```powershell
cd backend
python api_server.py
```

## API Overview

Important endpoints exposed by FastAPI:

### Public diagnostics

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

## Data And Runtime Artifacts

Common generated files and directories:

- `backend/data/agent.log`
- `backend/data/list.xlsx`
- `backend/data/agent_context.jsonl`
- `backend/data/agent_context_<run_id>.jsonl`
- `backend/data/runtime_browser_profiles/`
- `backend/data/runtime_resumes/`
- `backend/data/debug/`

These files are useful for debugging what happened during a run.

## Testing

Run backend tests:

```powershell
cd backend
pytest -q
```

Useful targeted tests:

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
```

If `vite build` has environment-specific process-spawn issues on your machine, a TypeScript-only check is still useful:

```powershell
cd frontend
npx tsc -b
```

## Troubleshooting

### MongoDB shows `ok=False`

Check:

- `MONGODB_URI`
- Atlas IP allowlist
- username/password
- cluster availability

Use:

- `GET /api/v1/startup`

to inspect the exact backend startup diagnostics.

### Firebase login fails

Check:

- frontend Firebase env vars
- backend `serviceAccountKey.json`
- local system clock

### Frontend says `Failed to fetch`

Usually means:

- backend is not running
- frontend points to the wrong `VITE_API_BASE_URL`
- CORS origin is missing

### LinkedIn scraper or submission loses session

The FastAPI path now uses a shared run-scoped browser profile so scraper and submission can reuse the same LinkedIn session.

Look for these logs:

- `Using shared runtime browser profile: ...`

If you see temporary profile logs during a frontend-triggered run, the runtime handoff is not behaving as expected.

### Telegram auto delivery is false

That means Telegram is configured but automatic sending is disabled for the current process, usually because:

- `TELEGRAM_ENABLED=false`

### Playwright opens LinkedIn feed but does not apply

That usually means LinkedIn login succeeded but the browser was redirected away from the real target job page. The submission agent now validates that it has recovered an actual `/jobs/view/...` page before continuing.

## Security Notes

- Do not commit `backend/.env`
- Do not commit real frontend `.env`
- Do not commit production Firebase secrets casually
- Do not expose LinkedIn credentials publicly
- Treat `backend/serviceAccountKey.json` as sensitive

## Recommended Development Workflow

1. Start MongoDB-backed backend first.
2. Confirm startup diagnostics from `/api/v1/startup`.
3. Start the frontend.
4. Log in with Google.
5. Complete onboarding with LinkedIn credentials and resume upload.
6. Run the pipeline in dry-run mode first.
7. Move to real submission after scraping, scoring, and submission logs look healthy.

## Commands Cheat Sheet

Backend install:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

Backend run:

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Frontend install:

```powershell
cd frontend
npm install
```

Frontend run:

```powershell
cd frontend
npm run dev
```

CLI run:

```powershell
cd backend
python main.py
```

Tests:

```powershell
cd backend
pytest -q
```

This README is meant to be the main project guide. The smaller frontend docs can still be useful, but this file should be the best starting point for understanding and running the full system.
