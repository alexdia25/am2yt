"""Search YouTube Music without logging in.

The only module that imports ytmusicapi. `YTMusic()` takes no arguments -- no
cookies, no OAuth, no API key -- which is the whole point of the design: the
tool must work with nothing but a playlist URL.

Search results are mapped straight to `Candidate` so nothing downstream has to
know ytmusicapi's result shape. Results we cannot play (no videoId) are dropped
here rather than becoming a broken entry in the final playlist.
"""

from __future__ import annotations

from collections.abc import Callable

from models import Candidate

DEFAULT_LIMIT = 5

_FILTER = "songs"


def to_candidates(results: list[dict] | None) -> list[Candidate]:
    """Map ytmusicapi search results to candidates, best-first order kept."""
    candidates = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        video_id = result.get("videoId")
        if not video_id:
            continue
        candidates.append(
            Candidate(
                video_id=video_id,
                title=result.get("title") or "",
                artist=_artist(result.get("artists")),
                album=_album(result.get("album")),
                duration_s=result.get("duration_seconds"),
            )
        )
    return candidates


def make_search(client=None, limit: int = DEFAULT_LIMIT) -> Callable[[str], list[Candidate]]:
    """Build the search callable `matching.resolve` expects.

    The client is created lazily so importing this module -- and running the
    tests -- never touches the network.
    """
    holder = {"client": client}

    def search(query: str) -> list[Candidate]:
        if holder["client"] is None:
            holder["client"] = _default_client()
        results = holder["client"].search(query, filter=_FILTER, limit=limit)
        return to_candidates(results)

    return search


def _default_client():
    from ytmusicapi import YTMusic

    return YTMusic()


def _artist(artists: object) -> str:
    """Join credited artists the way YouTube Music shows them."""
    if not isinstance(artists, list):
        return ""
    names = [
        entry.get("name", "")
        for entry in artists
        if isinstance(entry, dict) and entry.get("name")
    ]
    return ", ".join(names)


def _album(album: object) -> str | None:
    if isinstance(album, dict):
        return album.get("name") or None
    if isinstance(album, str):
        return album or None
    return None
