#!/usr/bin/env bash
set -e

# Change to project root directory
cd "$(dirname "$0")"

echo "====================================================="
echo "   🚀 Starting MangaDrop + Cloudflare Public Tunnel  "
echo "====================================================="

PORT=8000

# 1. Automatically free port 8000 if previously in use
PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Freeing port $PORT (killing old process $PID)..."
    kill -9 $PID 2>/dev/null || true
    sleep 0.5
fi

# 2. Ensure virtualenv exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install -q -r requirements.txt
fi

# 3. Start MangaDrop backend in background
echo "Starting MangaDrop Turbo Server on port $PORT..."
./venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port $PORT &
SERVER_PID=$!

# Ensure cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down MangaDrop..."
    kill -9 $SERVER_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Wait for server to start
sleep 2

# 4. Start Cloudflare Tunnel and expose public HTTPS link
echo ""
echo "✨ Exposing your Mac to the internet for Phone & Kindle..."
echo "-----------------------------------------------------"
npx cloudflared tunnel --url http://localhost:$PORT
