"""Pseudonymise playlist titles before anything is published.

This repo is public. Track titles, artist names and cluster names are the
substance of the analysis and stay as they are. **Playlist titles carry nothing
the analysis needs** - every metric that uses them (ARI, NMI, purity) treats
them as opaque group labels - and several are personal. So they are replaced
with stable pseudonyms everywhere they could surface: notebook outputs, README
tables, chart labels, cluster summaries.

The real-name mapping is written to `data/playlist_aliases.json`, which is
gitignored. Nothing here changes the database; redaction happens at the
presentation boundary so the analysis is unaffected.

    >>> alias("Sex Playlist ...")
    'Playlist K'
"""
from __future__ import annotations

import json
import sqlite3
import string

from . import config

ALIAS_PATH = config.DATA_DIR / "playlist_aliases.json"
PREFIX = "Playlist "


def _label(index: int) -> str:
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA'."""
    letters = string.ascii_uppercase
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = letters[rem] + out
    return out


def build_aliases(names) -> dict[str, str]:
    """Assign pseudonyms in sorted order so they are stable across runs."""
    unique = sorted({str(n) for n in names if n is not None})
    return {name: PREFIX + _label(i) for i, name in enumerate(unique)}


def save_aliases(mapping: dict[str, str]) -> None:
    ALIAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALIAS_PATH.write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_aliases() -> dict[str, str]:
    if not ALIAS_PATH.exists():
        return {}
    try:
        return json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def aliases_for(conn: sqlite3.Connection, refresh: bool = False) -> dict[str, str]:
    """Mapping for every playlist name in the database, cached on disk."""
    names = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT playlist_name FROM playlist_tracks "
            "UNION SELECT DISTINCT title FROM playlists WHERE title IS NOT NULL"
        )
    ]
    mapping = {} if refresh else load_aliases()
    missing = [n for n in names if n is not None and n not in mapping]
    if missing:
        mapping = build_aliases(list(mapping) + names)
        save_aliases(mapping)
    return mapping


def alias(name, mapping: dict[str, str] | None = None) -> str:
    """Pseudonym for one playlist title. Unknown names never leak through."""
    if name is None:
        return "(none)"
    mapping = load_aliases() if mapping is None else mapping
    return mapping.get(str(name), PREFIX + "?")


def redact_series(series, mapping: dict[str, str] | None = None):
    mapping = load_aliases() if mapping is None else mapping
    return series.map(lambda v: alias(v, mapping))
