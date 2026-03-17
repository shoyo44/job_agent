# Job Agent Frontend (Vite + React + TypeScript)

Professional modern-minimalist frontend for the FastAPI backend in `../backend`.

## Project Structure

```text
frontend/
  public/
  src/
    components/
      ConsoleDashboard.tsx
    config/
      firebase.ts
    hooks/
      useRunForm.ts
    services/
      api.ts
    types/
      api.ts
    utils/
      json.ts
    App.tsx
    App.css
    index.css
    main.tsx
```

## What This UI Covers

- Firebase Google login
- Backend token verification (`POST /api/v1/auth/firebase-login`)
- Public diagnostics:
  - `GET /api/v1/health`
  - `GET /api/v1/startup`
  - `GET /api/v1/config`
- Protected APIs:
  - `GET /api/v1/me`
  - `GET /api/v1/tracker/stats`
- Pipeline execution:
  - `POST /api/v1/run` (sync)
  - `POST /api/v1/run/async`
  - `GET /api/v1/run/{run_id}`

## Environment

Create `.env` in `frontend/` from `.env.example`.

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_STORAGE_BUCKET=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...
VITE_FIREBASE_MEASUREMENT_ID=...
```

Important:
- Do not hardcode Firebase keys in source files.
- Frontend uses Firebase Web App config from env vars.
- Backend uses `serviceAccountKey.json` separately.

## Run

1. Start backend first:

```bash
cd backend
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

2. Start frontend:

```bash
cd frontend
npm install
npm run dev
```

3. Open the Vite URL shown in terminal (usually `http://127.0.0.1:5173`).

## Notes

- Protected actions require Google sign-in first.
- If CORS issues appear, set `FRONTEND_ORIGINS` in backend config to include your frontend URL.
- UI theme is based on your `SKILL.md` + `modern-minimalist.md` guidance.
