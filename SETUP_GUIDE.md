# Setup Guide

This file is the practical setup companion to the main [README.md](/d:/Projects/Job%20Agent/README.md).

Use this guide if you want a direct, step-by-step path from a fresh clone to a working local run.

## Goal

By the end of this guide, you should be able to:

- run the FastAPI backend on `http://127.0.0.1:8000`
- run the frontend on `http://127.0.0.1:5173`
- sign in with Google
- start a pipeline run from the frontend

## Prerequisites

Install these first:

- Python 3.11 or newer
- Node.js 20 or newer
- npm 10 or newer
- a Firebase project for Google sign-in
- a LinkedIn account

Optional but recommended:

- MongoDB Atlas or local MongoDB
- Telegram bot token and chat ID

## Step 1: Clone the project

```powershell
git clone <your-repo-url>
cd "Job Agent"
```

## Step 2: Create a Python virtual environment

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

## Step 3: Install backend dependencies

From the project root:

```powershell
pip install -r requirements.txt
```

This installs the packages listed in:

- [requirements.txt](/d:/Projects/Job%20Agent/requirements.txt)
- [backend/requirements.txt](/d:/Projects/Job%20Agent/backend/requirements.txt)

## Step 4: Install Playwright Chromium

This project uses Playwright for LinkedIn scraping and submission.

```powershell
python -m playwright install chromium
```

If that is not enough on your machine, run:

```powershell
python -m playwright install
```

## Step 5: Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

## Step 6: Create the backend environment file

Create:

- `backend/.env`

You can base it on the following template.

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

Notes:

- `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` can also be entered at runtime from the frontend.
- `USER_RESUME_PATH` should point to a real PDF resume.
- MongoDB is optional, but recommended.
- Telegram is optional.

## Step 7: Add your resume

Place your resume PDF at:

- `backend/data/resume.pdf`

or update `USER_RESUME_PATH` in `backend/.env` to the correct file.

## Step 8: Add Firebase Admin credentials for the backend

Place the Firebase Admin service account JSON file here:

- `backend/serviceAccountKey.json`

The backend uses that file to verify Firebase ID tokens sent by the frontend.

## Step 9: Create the frontend environment file

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

These values come from your Firebase web app configuration.

## Step 10: Start the backend

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Expected result:

- FastAPI starts successfully
- startup diagnostics appear in the terminal

Useful checks:

- `http://127.0.0.1:8000/api/v1/health`
- `http://127.0.0.1:8000/api/v1/startup`

If MongoDB or Cloudflare is misconfigured, `/api/v1/startup` will help explain it.

## Step 11: Start the frontend

Open a new terminal:

```powershell
cd frontend
npm run dev
```

Then open:

- `http://127.0.0.1:5173`

## Step 12: Complete onboarding

In the frontend:

1. Sign in with Google
2. Enter LinkedIn email and password if not already in backend `.env`
3. Upload your resume
4. Confirm onboarding

## Step 13: Run a safe first test

For the first run, use:

- `dry_run = true`
- `easy_apply_only = true`

Suggested goal:

- `AI Engineer in Bangalore`

This is safer than starting with live submission immediately.

## Step 14: Run a real submission

Once dry-run works:

- set `dry_run = false`
- keep `easy_apply_only = true`

The current pipeline behavior is:

- scrape matching jobs
- score top 5
- critic keeps top 3
- submission tries finalists in order
- stop after 1 successful application

## Recommended verification checklist

Before blaming the frontend, confirm these:

### Backend checks

- `GET /api/v1/health` works
- `GET /api/v1/startup` works
- Firebase shows ready
- MongoDB shows ready if configured

### Frontend checks

- `VITE_API_BASE_URL` points to the correct backend port
- Google sign-in works
- onboarding completes

### LinkedIn checks

- LinkedIn credentials are valid
- Playwright Chromium is installed
- the logs show scraping and submission using the expected runtime browser flow

## Common commands

### Install everything

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cd frontend
npm install
```

### Run backend

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Run frontend

```powershell
cd frontend
npm run dev
```

### Run CLI version

```powershell
cd backend
python main.py
```

### Run tests

```powershell
cd backend
pytest -q
```

## Troubleshooting quick notes

### `Failed to fetch`

Usually means:

- backend is not running
- frontend is pointing to the wrong backend URL
- CORS mismatch

### `Mongo(ok=False)`

Usually means:

- bad `MONGODB_URI`
- Atlas IP allowlist problem
- auth problem

### Firebase login fails

Check:

- frontend Firebase env vars
- backend `serviceAccountKey.json`
- local system time

### LinkedIn goes to feed instead of applying

That usually means LinkedIn login succeeded but the session was not restored cleanly onto the actual target job page. The backend now tries to validate that it returned to a real `/jobs/view/...` page before continuing.

## Related files

- [README.md](/d:/Projects/Job%20Agent/README.md)
- [backend/config.py](/d:/Projects/Job%20Agent/backend/config.py)
- [backend/api/app.py](/d:/Projects/Job%20Agent/backend/api/app.py)
- [backend/api/service.py](/d:/Projects/Job%20Agent/backend/api/service.py)
- [frontend/src/services/api.ts](/d:/Projects/Job%20Agent/frontend/src/services/api.ts)

If you want to onboard a new teammate, send them this file first and the main README second.
