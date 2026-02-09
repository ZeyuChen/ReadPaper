#!/bin/bash

# ReadPaper Local Development Launcher (Conda)
# Usage: ./run_conda_local.sh

# 1. Cleanup old processes
echo "Cleaning up old processes..."
pkill -f "uvicorn" || true
pkill -f "next dev" || true

# Source environment variables if present
if [ -f .env ]; then
    echo "Loading .env..."
    set -a
    source .env
    set +a
fi

# Ensure Conda environment is used
# We assume 'readpaper' environment is created.
# We use 'conda run -n readpaper' to execute commands in the environment.

echo "Using Conda environment: readpaper"

# 2. Start Backend
echo "Starting Backend on port 8000..."
# Run uvicorn via conda
conda run -n readpaper --no-capture-output python -m uvicorn app.backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# 3. Start Frontend
echo "Starting Frontend on port 3000..."
cd app/frontend
# Run npm via conda (which should have node/npm in path if installed there, or use system)
# If node is in conda env 'readpaper', 'conda run' adds it to PATH.
conda run -n readpaper --no-capture-output npm run dev &
FRONTEND_PID=$!

# 4. Wait
echo "Services running."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "Press CTRL+C to stop."

wait $BACKEND_PID $FRONTEND_PID
