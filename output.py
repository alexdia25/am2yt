"""Write down what we found and hand back a YouTube playlist URL.

watch_videos is the trick that keeps this tool auth-free: YouTube builds a
temporary playlist from a list of video IDs with no credentials at all. It takes
at most 50 IDs per URL, so longer runs produce several separate playlists.

The playlist is temporary until the user clicks Save in the YouTube UI. Every
place we print a URL says so.
"""

from __future__ import annotations

import re
from pathlib import Path

from models import Result, format_duration_s

CHUNK_SIZE = 50
WATCH_VIDEOS = "https://www.youtube.com/watch_videos?video_ids="
WATCH = "https://www.youtube.com/watch?v="
SAVE_REMINDER = (
    "This playlist is temporary. Open it and click Save to keep it on your account."
)

_APOSTROPHE = re.compile(r"['’`]")
_UNSAFE = re.compile(r"[^a-z0-9]+")


def watch_videos_urls(video_ids: list[str]) -> list[str]:
    """Build one temporary-playlist URL per 50 video IDs."""
    chunks = [
        video_ids[start : start + CHUNK_SIZE]
        for start in range(0, len(video_ids), CHUNK_SIZE)
    ]
    return [WATCH_VIDEOS + ",".join(chunk) for chunk in chunks]


def slugify(name: str) -> str:
    """Turn a playlist name into a safe filename stem.

    Apostrophes are deleted rather than replaced, so Apple's curly-quoted
    "Today's Hits" becomes todays-hits and not today-s-hits.
    """
    slug = _UNSAFE.sub("-", _APOSTROPHE.sub("", name.lower())).strip("-")
    return slug or "playlist"


def results_markdown(playlist_name: str, results: list[Result], urls: list[str]) -> str:
    """Render the results file: the playlist URLs, then every track in order."""
    matched = [result for result in results if result.matched]
    skipped = [result for result in results if not result.matched]

    lines = [
        f"# {playlist_name}",
        "",
        f"{len(matched)} matched, {len(skipped)} skipped.",
        "",
    ]

    if urls:
        lines.append("## YouTube playlist")
        lines.append("")
        for index, url in enumerate(urls, start=1):
            label = f"Playlist {index} of {len(urls)}" if len(urls) > 1 else "Playlist"
            lines.append(f"- {label}: {url}")
        lines.append("")
        lines.append(SAVE_REMINDER)
        lines.append("")

    lines.append("## Tracks")
    lines.append("")
    for position, result in enumerate(results, start=1):
        lines.append(f"{position}. {_track_line(result)}")

    return "\n".join(lines) + "\n"


def write_results(
    playlist_name: str,
    results: list[Result],
    urls: list[str],
    directory: Path | None = None,
) -> Path:
    """Write the results markdown next to wherever the tool was run."""
    directory = Path(directory) if directory is not None else Path.cwd()
    path = directory / f"{slugify(playlist_name)}.md"
    path.write_text(results_markdown(playlist_name, results, urls), encoding="utf-8")
    return path


def _track_line(result: Result) -> str:
    track = result.track
    source = f"**{track.title}** — {track.artist}"
    if not result.candidate:
        return f"{source} → _no match_"

    candidate = result.candidate
    link = f"[{candidate.title} — {candidate.artist}]({WATCH}{candidate.video_id})"
    line = f"{source} → {link} [{format_duration_s(candidate.duration_s)}]"
    if result.from_cache:
        return f"{line} _(cached)_"
    if not result.confident:
        return f"{line} ⚠️ _low confidence_"
    return line
