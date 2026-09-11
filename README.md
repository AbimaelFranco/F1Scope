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

## Code conventions

Linting and formatting are handled by [Ruff](https://docs.astral.sh/ruff/) (config in
`pyproject.toml`). Run both before committing:

```bash
ruff check .           # lint
ruff format .          # auto-format
```

- `requirements.txt` — runtime dependencies only.
- `requirements-dev.txt` — adds dev/test tooling (Ruff, pytest) on top of the runtime ones.
- Commits follow the standardized pipeline in `.claude/skills/commit/` (branch check,
  security scan, one atomic commit per logical change, referencing the GitHub issue it
  advances).
