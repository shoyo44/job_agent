# Commands

This file is the operational command cookbook for Job Agent.

For full architecture and behavior context:

- [README.md](/d:/Projects/Job%20Agent/README.md)
- [SETUP_GUIDE.md](/d:/Projects/Job%20Agent/SETUP_GUIDE.md)

## Conventions

- Run commands from project root unless noted.
- Backend commands assume virtual environment is active.
- URLs assume default local ports.

## 1) Environment Setup

Create and activate virtual environment:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

Check Python and pip:

```powershell
python --version
pip --version
```

## 2) Install Dependencies

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Install Playwright Chromium:

```powershell
python -m playwright install chromium
```

Install all Playwright browsers (fallback):

```powershell
python -m playwright install
```

Install frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

## 3) Run Backend

Start FastAPI API server:

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Run helper entrypoint:

```powershell
cd backend
python api_server.py
```

Run CLI pipeline mode:

```powershell
cd backend
python main.py
```

## 4) Run Frontend

Start dev server:

```powershell
cd frontend
npm run dev
```

Build frontend:

```powershell
cd frontend
npm run build
```

Lint frontend:

```powershell
cd frontend
npm run lint
```

Run TypeScript build check:

```powershell
cd frontend
npx tsc -b
```

## 5) Test Commands

Run all backend tests:

```powershell
cd backend
pytest -q
```

Run targeted backend tests:

```powershell
cd backend
pytest tests/test_manager_agent.py -q
pytest tests/test_planner_agent.py -q
pytest tests/test_tracker_agent.py -q
pytest tests/test_integration_dry_run.py -q
```

## 6) Useful API URLs

Health:

```text
http://127.0.0.1:8000/api/v1/health
```

Startup diagnostics:

```text
http://127.0.0.1:8000/api/v1/startup
```

Frontend:

```text
http://127.0.0.1:5173
```

## 7) Typical Local Workflow

1. Activate virtual environment.
2. Start backend.
3. Open startup diagnostics and verify dependencies.
4. Start frontend in a second terminal.
5. Sign in with Google and complete onboarding.
6. Run dry-run pipeline first.
7. Move to real submission once logs and scoring look healthy.

## 8) First-Run Script (Manual Sequence)

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cd frontend
npm install
cd ..
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

In another terminal:

```powershell
cd frontend
npm run dev
```

## 9) Debug and Inspection Commands

Inspect backend startup status quickly:

```powershell
curl http://127.0.0.1:8000/api/v1/startup
```

Inspect run status by ID:

```powershell
curl http://127.0.0.1:8000/api/v1/run/<run_id>
```

Inspect tracker stats:

```powershell
curl http://127.0.0.1:8000/api/v1/tracker/stats
```

## 10) Common Problem Patterns

If frontend shows `Failed to fetch`:

- confirm backend terminal is running
- confirm `VITE_API_BASE_URL` points to backend
- confirm CORS allows frontend origin

If startup diagnostics show Mongo not ready:

- verify `MONGODB_URI`
- verify Atlas IP allowlist
- verify username/password

If Firebase auth fails:

- verify `frontend/.env` Firebase values
- verify `backend/serviceAccountKey.json`
- verify local machine time sync
