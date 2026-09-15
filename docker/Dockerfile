# F1Scope — Flask app image (#22).
#
# Slim base: Flask + requests + gunicorn are all pure Python, no compiled
# extensions, so there's nothing here that needs build-essential or any
# other system package beyond what python:3.11-slim already has.
#
# Build context is the repo root (see docker-compose.yml's `build.context`
# and `build.dockerfile`), so paths below are relative to the repo root,
# not this docker/ directory.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, in their own layer, so `docker build` doesn't
# reinstall them on every app-code change — only when requirements.txt
# itself changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY wsgi.py .

# Runs as a non-root user: the app only ever needs write access to
# instance/cache (the OpenF1 ingestion cache, mounted as a volume in
# docker-compose.yml — see #23), nothing else.
RUN useradd --create-home --uid 1000 f1scope \
    && mkdir -p instance/cache \
    && chown -R f1scope:f1scope /app
USER f1scope

# Unbuffered stdout so `docker logs` shows Flask/gunicorn output as it
# happens instead of batched on buffer flush.
ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

EXPOSE 5000

# Flask's own dev server (used for local `python wsgi.py`) explicitly
# warns it isn't meant for this — gunicorn is the production WSGI server.
# 2 workers is a reasonable default for a single-container deployment;
# tune via docker-compose command override if needed.
#
# --timeout 300: a *first-time* session ingestion (SessionCache's
# "ingest once, ever" cache miss path — see app/services/ingestion.py)
# makes ~50 OpenF1 requests (10 shared endpoints + 2 per-driver endpoints
# x ~20 drivers), throttled to OpenF1's free-tier 30 req/min limit. That's
# 100s+ just from rate limiting, before real response latency or
# exponential-backoff retries — gunicorn's 30s default worker timeout
# kills the request mid-ingestion (verified: a cold container against an
# uncached session_key 500s at exactly 30s). 300s covers a realistic
# worst case with real margin; subsequent requests for the same session
# hit the cache and return immediately regardless of this value.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "wsgi:app"]
