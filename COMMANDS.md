# Commands

This file is a quick command cheat sheet for the project.

For full explanation, use:

- [README.md](/d:/Projects/Job%20Agent/README.md)
- [SETUP_GUIDE.md](/d:/Projects/Job%20Agent/SETUP_GUIDE.md)

## Python environment

Create a virtual environment:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

## Install dependencies

Install Python packages from the project root:

```powershell
pip install -r requirements.txt
```

Install Playwright Chromium:

```powershell
python -m playwright install chromium
```

Install frontend packages:

```powershell
cd frontend
npm install
```

## Run backend

Start FastAPI backend:

```powershell
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Run backend helper entrypoint:

```powershell
cd backend
python api_server.py
```

Run CLI pipeline:

```powershell
cd backend
python main.py
```

## Run frontend

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

TypeScript check:

```powershell
cd frontend
npx tsc -b
```

## Run tests

Run all backend tests:

```powershell
cd backend
pytest -q
```

Run selected backend tests:

```powershell
cd backend
pytest tests/test_manager_agent.py -q
pytest tests/test_planner_agent.py -q
pytest tests/test_tracker_agent.py -q
pytest tests/test_integration_dry_run.py -q
```

## Helpful URLs

Backend health:

```text
http://127.0.0.1:8000/api/v1/health
```

Backend startup diagnostics:

```text
http://127.0.0.1:8000/api/v1/startup
```

Frontend:

```text
http://127.0.0.1:5173
```

## Typical workflow

1. Activate virtual environment
2. Start backend
3. Start frontend
4. Sign in with Google
5. Complete onboarding
6. Run pipeline

## Recommended first-run sequence

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
