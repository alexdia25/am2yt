"""Remember which video we picked for which Apple Music track.

Keyed by Apple's storeAdamID. A cache hit skips both the search and the prompt,
which is what makes reruns cheap -- and it means a lost temporary playlist can
be regenerated instantly.

A damaged cache is never fatal: unreadable files and malformed entries are
dropped, because the worst case is redoing work we already did once.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from models import Candidate

DEFAULT_PATH = Path.home() / ".am2yt" / "cache.json"

_FIELDS = {field.name for field in fields(Candidate)}


def load(path: Path = DEFAULT_PATH) -> dict[str, Candidate]:
    """Read cached matches. Returns {} if the file is missing or unusable."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    entries = {}
    for key, value in raw.items():
        candidate = _candidate(value)
        if candidate:
            entries[str(key)] = candidate
    return entries


def save(entries: dict[str, Candidate], path: Path = DEFAULT_PATH) -> None:
    """Write cached matches, replacing whatever was there."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {key: asdict(candidate) for key, candidate in entries.items()},
        indent=2,
        ensure_ascii=False,
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _candidate(value: object) -> Candidate | None:
    if not isinstance(value, dict) or not value.get("video_id"):
        return None
    known = {key: value[key] for key in _FIELDS if key in value}
    try:
        return Candidate(**known)
    except TypeError:
        return None
