#!/bin/bash

# ReadPaper Local Development Launcher

# 1. Cleanup old processes
echo "Cleaning up old processes..."
pkill -f "uvicorn" || true
pkill -f "next dev" || true

# 2. Start Backend
echo "Starting Backend on port 8000..."
source .env
export DISABLE_AUTH=true
# Use venv python if available, else system python
PYTHON_CMD="python"
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
fi

$PYTHON_CMD -m uvicorn app.backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# 3. Start Frontend
echo "Starting Frontend on port 3000..."
cd app/frontend
npm run dev &
FRONTEND_PID=$!

# 4. Wait
echo "Services running. Backend: http://localhost:8000, Frontend: http://localhost:3000"
echo "Press CTRL+C to stop."
wait $BACKEND_PID $FRONTEND_PID
