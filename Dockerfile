FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    mitmproxy==10.3.1 \
    fastapi==0.111.0 \
    uvicorn[standard]==0.29.0 \
    requests==2.31.0 \
    sse-starlette==2.0.0

# Generate CA cert BEFORE copying code.
# This layer is Docker-cached — cert never changes unless pip packages change.
RUN timeout 5 mitmdump -p 19999 --quiet 2>/dev/null || true

WORKDIR /app
COPY addon.py cookie_manager.py admin.py start.sh ./
RUN chmod +x start.sh

EXPOSE 8080
EXPOSE 8888

CMD ["./start.sh"]
