"""Scrape a public Apple Music playlist page.

The page embeds its data in a <script id="serialized-server-data"> tag. Tracks
live in the section whose itemKind is "trackLockup", and only the first 50 are
embedded regardless of playlist length -- the footer section reports the real
total so callers can warn about truncation.

This module is the only place that knows the page's shape. If Apple changes it,
this is the file that breaks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

from models import Track

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TIMEOUT_S = 30

_SERVER_DATA = re.compile(
    r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.DOTALL
)
_SONG_COUNT = re.compile(r"(\d+)\s+songs?", re.IGNORECASE)

_TRACK_SECTION = "trackLockup"
_HEADER_SECTION = "containerDetailHeaderLockup"
_FOOTER_SECTION = "containerDetailTracklistFooterLockup"


class AppleError(Exception):
    """Base class for everything this module raises."""


class AppleFetchError(AppleError):
    """The playlist page could not be retrieved."""


class AppleParseError(AppleError):
    """The page was retrieved but did not look like we expect."""


@dataclass(frozen=True)
class Playlist:
    name: str
    tracks: list[Track]
    reported_total: int | None = None

    @property
    def truncated(self) -> bool:
        return (
            self.reported_total is not None
            and self.reported_total > len(self.tracks)
        )


def fetch_playlist(url: str) -> Playlist:
    """GET an Apple Music playlist URL and parse it."""
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AppleFetchError(f"Could not fetch {url}: {exc}") from exc

    # Apple serves UTF-8 but does not always say so in Content-Type, and requests
    # then falls back to Latin-1 -- which turns the curly apostrophe in a name
    # like "Today's Hits" into mojibake. The page is always UTF-8, so say so.
    response.encoding = response.apparent_encoding or "utf-8"
    return parse_playlist(response.text)


def parse_playlist(html: str) -> Playlist:
    """Extract the playlist name, tracks, and reported total from page HTML."""
    sections = _sections(_server_data(html))
    return Playlist(
        name=_playlist_name(sections),
        tracks=_tracks(sections),
        reported_total=_reported_total(sections),
    )


def _server_data(html: str) -> dict:
    match = _SERVER_DATA.search(html)
    if not match:
        raise AppleParseError(
            "No serialized-server-data script tag in the page. Either this is "
            "not a public Apple Music playlist page, or Apple changed the page."
        )
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise AppleParseError(f"serialized-server-data is not valid JSON: {exc}") from exc


def _sections(data: dict) -> list[dict]:
    try:
        sections = data["data"][0]["data"]["sections"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AppleParseError(
            f"Unexpected page structure at data[0].data.sections: {exc}"
        ) from exc
    if not isinstance(sections, list):
        raise AppleParseError("Unexpected page structure: sections is not a list")
    return sections


def _section(sections: list[dict], item_kind: str) -> dict | None:
    for section in sections:
        if isinstance(section, dict) and section.get("itemKind") == item_kind:
            return section
    return None


def _items(sections: list[dict], item_kind: str) -> list[dict]:
    section = _section(sections, item_kind)
    if not section:
        return []
    items = section.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _playlist_name(sections: list[dict]) -> str:
    header = _items(sections, _HEADER_SECTION)
    if header and header[0].get("title"):
        return str(header[0]["title"])
    return "Apple Music playlist"


def _reported_total(sections: list[dict]) -> int | None:
    footer = _items(sections, _FOOTER_SECTION)
    if not footer:
        return None
    match = _SONG_COUNT.search(str(footer[0].get("description") or ""))
    return int(match.group(1)) if match else None


def _tracks(sections: list[dict]) -> list[Track]:
    items = _items(sections, _TRACK_SECTION)
    if not items:
        raise AppleParseError(
            "No trackLockup section in the page -- found no tracks to convert."
        )
    tracks = [_track(item) for item in items]
    return [track for track in tracks if track is not None]


def _track(item: dict) -> Track | None:
    apple_id = _dig(item, "contentDescriptor", "identifiers", "storeAdamID")
    title = item.get("title")
    if not apple_id or not title:
        return None
    duration = item.get("duration")
    return Track(
        apple_id=str(apple_id),
        title=str(title),
        artist=_first_link_title(item.get("subtitleLinks")),
        album=_first_link_title(item.get("tertiaryLinks")) or None,
        duration_ms=int(duration) if isinstance(duration, int) else None,
    )


def _first_link_title(links: object) -> str:
    if isinstance(links, list) and links and isinstance(links[0], dict):
        return str(links[0].get("title") or "")
    return ""


def _dig(data: object, *keys: str) -> object | None:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data
