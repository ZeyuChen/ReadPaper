#!/bin/bash

# ReadPaper Local Development Launcher (Micromamba)
# Usage: ./run_micromamba_local.sh

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

# Ensure Micromamba environment is used
# We assume 'readpaper' environment is created.

# Try to detect MAMBA_ROOT_PREFIX if not set
if [ -z "$MAMBA_ROOT_PREFIX" ]; then
    # Common default locations
    if [ -d "$HOME/mamba" ]; then
        export MAMBA_ROOT_PREFIX="$HOME/mamba"
    elif [ -d "$HOME/micromamba" ]; then
        export MAMBA_ROOT_PREFIX="$HOME/micromamba"
    fi
fi

echo "Using Micromamba environment: readpaper (Root: ${MAMBA_ROOT_PREFIX:-default})"

# Disable Auth for Local Dev
export DISABLE_AUTH=true
export NEXT_PUBLIC_DISABLE_AUTH=true
export NEXTAUTH_SECRET="local-dev-secret-do-not-use-in-production"

# 2. Start Backend
echo "Starting Backend on port 8000..."
# Run uvicorn via micromamba
micromamba run -n readpaper python -m uvicorn app.backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# 3. Start Frontend
echo "Starting Frontend on port 3000..."
# We use a subshell to change directory only for the frontend command
(
    cd app/frontend
    # Run npm via micromamba (assuming node/npm is available in the environment or system path)
    micromamba run -n readpaper npm run dev
) &
FRONTEND_PID=$!

# 4. Wait
echo "Services running."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "Press CTRL+C to stop."

wait $BACKEND_PID $FRONTEND_PID
