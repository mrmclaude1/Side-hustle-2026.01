FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
# $PORT is honoured by most PaaS hosts; defaults to 8000 locally.
# --proxy-headers + forwarded-allow-ips='*' make request.base_url reflect the
# real https:// scheme/host behind the platform's TLS-terminating proxy
# (Render/Railway/Fly) — the canonical/og:image tags depend on it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
