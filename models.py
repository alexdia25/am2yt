"""Data passed between modules, and the formatters that render it.

This is the one module every other module may import. The duration helpers live
here rather than in matching.py because both matching.py and output.py need
them, and modules other than am2yt.py must not import each other.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    """One song from an Apple Music playlist."""

    apple_id: str
    title: str
    artist: str
    album: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class Candidate:
    """One YouTube Music search result."""

    video_id: str
    title: str
    artist: str
    album: str | None = None
    duration_s: int | None = None


@dataclass(frozen=True)
class Result:
    """What we decided about one track."""

    track: Track
    candidate: Candidate | None
    confident: bool
    from_cache: bool = False

    @property
    def matched(self) -> bool:
        return self.candidate is not None


def format_duration_s(seconds: int | None) -> str:
    """Render seconds as m:ss, or ?:?? when unknown."""
    if seconds is None:
        return "?:??"
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def format_duration_ms(milliseconds: int | None) -> str:
    """Render milliseconds as m:ss, or ?:?? when unknown."""
    if milliseconds is None:
        return "?:??"
    return format_duration_s(round(milliseconds / 1000))
