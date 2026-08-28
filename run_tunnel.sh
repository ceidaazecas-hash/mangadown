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
./venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port $PORT --reload &
SERVER_PID=$!

# Ensure cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down MangaDrop..."
    kill -9 $SERVER_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

sleep 2

# 4. Start Cloudflare Tunnel and automatically generate short Kindle link
echo ""
echo "✨ Generating your short Kindle & Phone Link..."
echo "-----------------------------------------------------"

./venv/bin/python3 -c "
import subprocess, re, sys

try:
    import httpx
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'httpx'], check=True)
    import httpx

def shorten(url):
    try:
        r = httpx.get('https://ulvis.net/API/write/get', params={'url': url, 'type': 'json'}, verify=False, timeout=4)
        if r.status_code == 200 and r.json().get('data', {}).get('url'):
            return r.json()['data']['url']
    except Exception:
        pass
    try:
        r = httpx.get('https://clck.ru/--', params={'url': url}, verify=False, timeout=4)
        if r.status_code == 200 and r.text.startswith('http'):
            return r.text.strip()
    except Exception:
        pass
    return url

proc = subprocess.Popen(['npx', 'cloudflared', 'tunnel', '--url', 'http://localhost:8000'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
short_printed = False

for line in proc.stdout:
    sys.stdout.write(line)
    sys.stdout.flush()
    if not short_printed and 'trycloudflare.com' in line:
        match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
        if match:
            tunnel_url = match.group(0)
            kindle_url = f'{tunnel_url}/k'
            short_link = shorten(kindle_url)
            print('\n' + '='*64)
            print('  📖 SHORT KINDLE URL (TYPE THIS ON YOUR KINDLE SCREEN):')
            print(f'  👉  {short_link}')
            print('='*64 + '\n', flush=True)
            short_printed = True
"
