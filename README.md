# F1Scope

Interactive 3D Formula 1 race replay and telemetry analysis powered by [OpenF1](https://openf1.org/).

See [DESCRIPTION.MD](DESCRIPTION.MD) for the project pitch, [docs/PLANNING.md](docs/PLANNING.md)
for the approved scope/architecture, and [docs/architecture/](docs/architecture/) for the
interactive architecture diagram.

## Stack

Python + Flask, packaged with Docker. Data comes from OpenF1's free-tier API (historical
sessions, 3 req/s / 30 req/min rate limit) — sessions are ingested once and served from a
local cache, never re-fetched per request. See `docs/PLANNING.md` for the full rationale.

## Project structure

```
app/
├── routes/     # Blueprints: web views (HTML) + internal JSON API (/api/...)
├── services/   # OpenF1 client, ingestion, cache (milestone E2)
├── models/     # Internal data structures/schemas
├── static/     # CSS/JS
└── templates/  # Jinja2 templates
docker/
├── Dockerfile          # Flask app image (gunicorn entrypoint)
└── docker-compose.yml  # One-command stack: builds the image, persists the cache volume
```

## Getting started

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

flask --app wsgi run
```

The app boots with a `development` config by default (see `app/config.py`); no API key is
needed for OpenF1's free tier.

## Running with Docker

The whole app — no local Python install needed — with one command from the repo root:

```bash
cp .env.example .env          # first time only; docker-compose reuses this file
docker compose -f docker/docker-compose.yml up --build
```

Then open http://localhost:5000.

- `docker/Dockerfile` builds a `python:3.11-slim` image running the app under
  [gunicorn](https://gunicorn.org/) (Flask's own dev server isn't meant for this — see the
  warning it prints when you run it directly).
- `docker/docker-compose.yml` publishes port 5000 and mounts a **named volume**
  (`f1scope-cache`, at `/app/instance/cache`) so sessions you've already ingested from OpenF1
  survive container restarts — `docker compose down` keeps it; `docker compose down -v` is
  the explicit opt-in to wipe it and start fresh.
- The **first** request for a given session is slow (a full ingestion makes ~50 rate-limited
  OpenF1 requests — up to a few minutes for a full race with 20 drivers); every request after
  that for the same `session_key` is served from the cache and is fast. This is expected, not
  a hang.
- Rebuild after changing `requirements.txt` or anything under `app/`:
  `docker compose -f docker/docker-compose.yml up --build`.

### Environment variables

Read from `.env` (see `.env.example`) both locally and inside the container — copy it once,
adjust as needed:

| Variable | Default | Notes |
|---|---|---|
| `FLASK_ENV` | `development` | The Docker image always runs as `production` regardless of this value (set explicitly in `docker-compose.yml`) — gunicorn is already the entrypoint, so the dev-server-only `development` mode has no effect there. |
| `SECRET_KEY` | `change-me-in-production` | Signs sessions/cookies. Set a real random value for any deployment reachable by anyone but you. |
| `OPENF1_BASE_URL` | `https://api.openf1.org/v1` | OpenF1 is a free, read-only, public API — no key required for v1. |
| `CACHE_DIR` | `instance/cache` | Where ingested sessions are cached. Inside Docker this resolves to `/app/instance/cache`, the path the named volume mounts over — change both together if you ever change one. |

## Code conventions

Linting and formatting are handled by [Ruff](https://docs.astral.sh/ruff/) (config in
`pyproject.toml`). Run both before committing:

```bash
ruff check .           # lint
ruff format .          # auto-format
```

- `requirements.txt` — runtime dependencies only (includes gunicorn, the Docker image's
  production WSGI server — not used by local `flask run`/`python wsgi.py`, but a runtime,
  not dev-only, dependency).
- `requirements-dev.txt` — adds dev/test tooling (Ruff, pytest) on top of the runtime ones.
- Commits follow the standardized pipeline in `.claude/skills/commit/` (branch check,
  security scan, one atomic commit per logical change, referencing the GitHub issue it
  advances).
