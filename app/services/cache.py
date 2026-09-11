"""Local on-disk cache for ingested OpenF1 sessions.

Each session is cached as a directory of JSON files under a cache root
(one file per SessionData field), so the rest of the app — replay,
telemetry, race HUD — always reads from disk and never re-hits OpenF1 per
request. See docs/PLANNING.md section 2 for the rationale.

Plain JSON files rather than SQLite: SessionData's fields are already the
raw record lists OpenF1 returns, so a direct file-per-field dump avoids
designing (and keeping in sync) a table schema per endpoint, for a
single-user local tool where "query by time range" doesn't exist yet.
Revisit if/when the replay/telemetry layers need indexed queries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.ingestion import SessionData, ingest_session
from app.services.openf1_client import OpenF1Client

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "_manifest.json"
_DATA_FIELDS = [f.name for f in fields(SessionData) if f.name != "session_key"]


class SessionCache:
    """Reads/writes :class:`SessionData` bundles as JSON files on disk."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)

    def _session_dir(self, session_key: int) -> Path:
        return self.cache_dir / str(session_key)

    def has(self, session_key: int) -> bool:
        """Whether ``session_key`` has already been ingested and cached."""
        return (self._session_dir(session_key) / _MANIFEST_FILENAME).is_file()

    def save(self, data: SessionData) -> None:
        """Persist a :class:`SessionData` bundle to disk, one JSON file per field."""
        session_dir = self._session_dir(data.session_key)
        session_dir.mkdir(parents=True, exist_ok=True)

        payload = asdict(data)
        for name in _DATA_FIELDS:
            self._write_json(session_dir / f"{name}.json", payload[name])

        self._write_json(
            session_dir / _MANIFEST_FILENAME,
            {"session_key": data.session_key, "cached_at": datetime.now(UTC).isoformat()},
        )
        logger.info("Cached session_key=%s at %s", data.session_key, session_dir)

    def load(self, session_key: int) -> SessionData:
        """Load a previously cached session. Raises ``FileNotFoundError`` if absent."""
        if not self.has(session_key):
            raise FileNotFoundError(f"No cached session for session_key={session_key!r}")

        session_dir = self._session_dir(session_key)
        values: dict[str, Any] = {"session_key": session_key}
        for name in _DATA_FIELDS:
            values[name] = self._read_json(session_dir / f"{name}.json")

        return SessionData(**values)

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))


def get_or_ingest_session(
    client: OpenF1Client, cache: SessionCache, session_key: int
) -> SessionData:
    """Return the cached session if present, otherwise ingest it once and cache it.

    This is the one entry point the rest of the app should use to obtain a
    session: it's what keeps OpenF1 requests down to "once per session,
    ever" instead of once per replay/telemetry request.
    """
    if cache.has(session_key):
        logger.info("Cache hit for session_key=%s", session_key)
        return cache.load(session_key)

    logger.info("Cache miss for session_key=%s — ingesting from OpenF1", session_key)
    data = ingest_session(client, session_key)
    cache.save(data)
    return data
