---
description: Run the Automated Job Agent Application
---
# Start Job Agent

This workflow starts the Python Backend API (FastAPI) and the React Frontend UI.

// turbo-all
1. Install Python dependencies including backend requirements
`pip install -r requirements.txt fastapi uvicorn`

2. Install React frontend dependencies
`cd job_agent && npm install`

3. Start the FastAPI backend server (runs in background)
`cd job_agent && uvicorn server:app --port 8001`

4. Start the React frontend development server
`cd job_agent && npm run dev`
