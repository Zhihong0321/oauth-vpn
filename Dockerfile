FROM python:3.11-slim

# System deps for mitmproxy
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

# Admin HTTP server (Railway public HTTP domain routes here)
EXPOSE 8080
# mitmproxy proxy port (Railway TCP proxy)
EXPOSE 8890

CMD ["./start.sh"]
