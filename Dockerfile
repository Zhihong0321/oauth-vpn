FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install mitmproxy FIRST and generate cert — cached separately from app deps
# Cert only regenerates if mitmproxy version changes
RUN pip install --no-cache-dir mitmproxy==10.3.1
RUN timeout 5 mitmdump -p 19999 --quiet 2>/dev/null || true

# Install remaining deps (changes here won't regenerate cert)
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn[standard]==0.29.0 \
    requests==2.31.0 \
    curl_cffi==0.7.3

WORKDIR /app
COPY addon.py cookie_manager.py admin.py start.sh ./
RUN chmod +x start.sh

EXPOSE 8080
EXPOSE 8888

CMD ["./start.sh"]
