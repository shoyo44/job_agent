# Setup Guide

This guide takes you from a fresh clone to a stable local environment for both backend and frontend flows.

For architecture and system-level understanding, use [README.md](/d:/Projects/Job%20Agent/README.md).
For quick command lookup, use [COMMANDS.md](/d:/Projects/Job%20Agent/COMMANDS.md).

## System Architecture Snapshot

The platform has four runtime layers:

1. Frontend (`React + Vite`): onboarding, run launch, live status, run results.
2. Backend API (`FastAPI`): auth validation, diagnostics, run orchestration endpoints.
3. Agent Pipeline: `Manager -> Planner -> Critic -> CoverLetter -> Submission -> Tracker`.
4. Integrations: LinkedIn (Playwright), Cloudflare Workers AI, Firebase Auth, MongoDB/Excel, Telegram.

```text
Frontend (5173)
   |
   | HTTPS + Firebase Bearer token
   v
FastAPI Backend (8000)
   |
   +--> ManagerAgent (goal/profile parsing)
   +--> PlannerAgent (query build + scoring)
   +--> CriticAgent (finalist selection)
   +--> CoverLetterAgent (tailored drafts)
   +--> SubmissionAgent (Easy Apply automation + fallback order)
   +--> TrackerAgent (MongoDB/Excel persistence)
   |
   +--> External systems: LinkedIn / Cloudflare AI / Firebase / Telegram
```

For full component and sequence diagrams, see:
- [README.md](/d:/Projects/Job%20Agent/README.md) -> `Clean System Architecture`

## What You Will Have At The End

By the end of this guide, you should be able to:

- run the backend at `http://127.0.0.1:8000`
- run the frontend at `http://127.0.0.1:5173`
- authenticate with Firebase Google sign-in
- start and monitor a pipeline run from the dashboard
- validate startup health and diagnose common failures

## Prerequisites

Required:

- Python 3.11+
- Node.js 20+
- npm 10+
- Firebase project with Google sign-in enabled
- LinkedIn account

Optional but recommended:

- MongoDB Atlas (or local MongoDB)
- Telegram bot token + chat ID

## Step 1: Clone the project

```powershell
git clone <your-repo-url>
cd "Job Agent"
```

## Step 2: Create and activate Python environment

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

Validation:

```powershell
python --version
pip --version
```

## Step 3: Install backend dependencies

From project root:

```powershell
pip install -r requirements.txt
```

Dependency sources:

- [requirements.txt](/d:/Projects/Job%20Agent/requirements.txt)
- [backend/requirements.txt](/d:/Projects/Job%20Agent/backend/requirements.txt)

## Step 4: Install Playwright browser runtime

```powershell
python -m playwright install chromium
```

If browser launch still fails on your machine:

```powershell
python -m playwright install
```

## Step 5: Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

Validation:

```powershell
cd frontend
npm ls --depth=0
cd ..
```

## Step 6: Configure backend environment

Create file:

- `backend/.env`

Suggested template:

```env
CF_ACCOUNT_ID=
CF_API_TOKEN=
CF_MODEL=@cf/meta/llama-3.1-8b-instruct

LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=

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

MIN_CONFIDENCE_SCORE=65
MAX_APPLICATIONS_PER_RUN=10
DRY_RUN=true

EXCEL_FILE_PATH=data/list.xlsx
LOG_FILE_PATH=data/agent.log
MONGODB_URI=
MONGODB_DB=job_agent
MONGODB_COLLECTION=applications

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ENABLED=false
TELEGRAM_POLL_TIMEOUT=30

CHROMIUM_PATH=
HEADLESS=false
HUMAN_DELAY_MS=1500
USE_TEMP_BROWSER_PROFILE=false
RUNTIME_BROWSER_PROFILE_DIR=
```

Important notes:

- `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` can also be supplied at runtime from frontend onboarding.
- `USER_RESUME_PATH` must point to a real PDF.
- MongoDB is optional, but strongly recommended for stable history/stats.
- Telegram is optional and should not block pipeline completion.

## Step 7: Add resume file

Place your resume at:

- `backend/data/resume.pdf`

If stored elsewhere, update `USER_RESUME_PATH`.

## Step 8: Configure Firebase Admin for backend

Place Firebase Admin service account JSON at:

- `backend/serviceAccountKey.json`

Used by backend to verify Firebase ID tokens from frontend requests.

## Step 9: Configure frontend environment

Create file:

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

All Firebase values come from your Firebase web app settings.

## Step 10: Start backend

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Expected startup checks:

- health endpoint responds
- startup diagnostics endpoint responds
- Firebase status is visible
- MongoDB status is visible if configured

Useful URLs:

- `http://127.0.0.1:8000/api/v1/health`
- `http://127.0.0.1:8000/api/v1/startup`

## Step 11: Start frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open:

- `http://127.0.0.1:5173`

## Step 12: Complete onboarding in UI

1. Sign in with Google.
2. Enter LinkedIn credentials if not already in backend `.env`.
3. Upload resume.
4. Confirm pipeline preferences.

## Step 13: Run safe first pipeline

Recommended first-run settings:

- `dry_run = true`
- `easy_apply_only = true`

Suggested goal example:

- `AI Engineer in Bangalore`

Why this is safer:

- validates parsing/scraping/scoring/selection without committing real applications

## Step 14: Move to live submission

After successful dry-run validation:

- switch `dry_run` to `false`
- keep `easy_apply_only = true` initially

Default live behavior:

- scrape jobs
- score top candidates
- select top finalists
- attempt submissions sequentially
- stop after configured success threshold

## Verification Checklist

Before investigating deeper issues, verify:

### Backend

- `GET /api/v1/health` works
- `GET /api/v1/startup` works
- Firebase status is healthy
- MongoDB status healthy (if configured)

### Frontend

- `VITE_API_BASE_URL` matches backend host/port
- Google sign-in works
- onboarding completes

### Automation

- Playwright browser installs successfully
- scraper and submission logs show expected run progression
- runtime browser profile handoff is visible in logs

## Common Commands

Install all dependencies:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cd frontend
npm install
```

Run backend:

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Run frontend:

```powershell
cd frontend
npm run dev
```

Run backend CLI mode:

```powershell
cd backend
python main.py
```

Run backend tests:

```powershell
cd backend
pytest -q
```

## Troubleshooting

### Frontend `Failed to fetch`

Likely causes:

- backend not running
- wrong `VITE_API_BASE_URL`
- CORS mismatch

### MongoDB `ok=False` in startup diagnostics

Likely causes:

- invalid `MONGODB_URI`
- Atlas allowlist/network issue
- auth credentials issue

### Firebase login fails

Check:

- frontend Firebase values
- backend `serviceAccountKey.json`
- local system clock skew

### LinkedIn navigates to feed instead of target job

Likely session restoration/handoff issue. Confirm logs indicate recovery to a valid `/jobs/view/...` URL before apply steps.

## Security Checklist

- do not commit `backend/.env`
- do not commit `frontend/.env`
- treat `backend/serviceAccountKey.json` as sensitive
- do not log or share LinkedIn credentials
- rotate API keys if leaked

## Related Files

- [README.md](/d:/Projects/Job%20Agent/README.md)
- [COMMANDS.md](/d:/Projects/Job%20Agent/COMMANDS.md)
- [config.py](/d:/Projects/Job%20Agent/backend/config.py)
- [app.py](/d:/Projects/Job%20Agent/backend/api/app.py)
- [service.py](/d:/Projects/Job%20Agent/backend/api/service.py)
- [api.ts](/d:/Projects/Job%20Agent/frontend/src/services/api.ts)
