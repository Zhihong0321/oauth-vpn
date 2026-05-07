FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    mitmproxy==10.3.1 \
    fastapi==0.111.0 \
    uvicorn[standard]==0.29.0 \
    requests==2.31.0

WORKDIR /app
COPY addon.py cookie_manager.py admin.py start.sh ./
RUN chmod +x start.sh

# Generate mitmproxy CA cert at BUILD TIME so it never changes on restart/redeploy.
# The cert is baked into the image — install it once and forget it.
RUN timeout 5 mitmdump -p 19999 --quiet 2>/dev/null || true && \
    echo "CA cert generated:" && ls /root/.mitmproxy/

EXPOSE 8080
EXPOSE 8888

CMD ["./start.sh"]
