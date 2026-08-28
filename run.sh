#!/usr/bin/env bash
set -e

# Change to script directory
cd "$(dirname "$0")"

echo "========================================="
echo "   🚀 Starting MangaDrop Web Server      "
echo "========================================="

# Free port 8000 if already in use by previous instances
PORT=8000
PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Freeing port $PORT (terminating process $PID)..."
    kill -9 $PID 2>/dev/null || true
    sleep 0.5
fi

# Ensure virtualenv exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Install/verify dependencies
./venv/bin/pip install -q -r requirements.txt

echo "Starting server on http://localhost:$PORT ..."
exec ./venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port $PORT
