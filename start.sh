#!/bin/sh
set -e

echo "[GemShare] Starting admin server on port ${PORT:-8000}..."
python admin.py &
ADMIN_PID=$!

# Give mitmproxy 3s to generate its CA cert before admin serves /cert
sleep 3

echo "[GemShare] Starting mitmproxy on port 8080..."
mitmdump \
  --listen-host 0.0.0.0 \
  --listen-port 8080 \
  --scripts addon.py \
  --set block_global=false \
  --set connection_strategy=lazy &
MITM_PID=$!

# If either process dies, kill both and exit (Railway will restart)
wait $ADMIN_PID $MITM_PID
