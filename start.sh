#!/bin/sh

echo "[GemShare] Starting admin on port ${PORT:-8080}..."
python admin.py &

# Give mitmproxy time to generate CA cert before admin serves /cert
sleep 5

echo "[GemShare] Starting mitmproxy on port 8888..."
# Loop so container stays alive if mitmproxy crashes
while true; do
  mitmdump \
    --listen-host 0.0.0.0 \
    --listen-port 8888 \
    -s addon.py \
    --set block_global=false
  echo "[GemShare] mitmproxy exited (code $?), restarting in 5s..."
  sleep 5
done
