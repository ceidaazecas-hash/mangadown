#!/usr/bin/env bash
set -e

# Change to project root directory
cd "$(dirname "$0")"

echo "====================================================="
echo "   🚀 Starting MangaDrop Turbo Local Server         "
echo "====================================================="

PORT=8000

# 1. Automatically free port 8000 if previously in use
PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Freeing port $PORT (killing old process $PID)..."
    kill -9 $PID 2>/dev/null || true
    sleep 0.5
fi

# 2. Ensure virtualenv exists & dependencies are installed
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

./venv/bin/pip install -q -r requirements.txt

# 3. Detect Local Network IP Address
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || ./venv/bin/python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "127.0.0.1")

echo ""
echo "✨ Server is LIVE and ready!"
echo "-----------------------------------------------------"
echo "  💻 Mac Browser:    http://localhost:$PORT"
echo "  📱 Kindle Wi-Fi:   http://$LOCAL_IP:$PORT/kindle"
echo "-----------------------------------------------------"
echo "Press CTRL+C to stop the server anytime."
echo ""

# 4. Launch FastAPI Turbo Server
exec ./venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port $PORT --reload
