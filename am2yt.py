#!/usr/bin/env python3
"""Turn a public Apple Music playlist into a YouTube playlist. No login needed.

Usage:
    am2yt.py <apple-music-playlist-url> [--open] [--no-cache]
    am2yt.py --set "<track title>" <video-id-or-link> [--set ...] [<url>]

Every quit path -- a `q` at a prompt, Ctrl-C, a run that matched nothing -- still
writes the cache and the results file, so no answered prompt is ever wasted.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import cache
from apple import AppleError, fetch_playlist
from matching import resolve, video_id
from models import Result
from output import watch_videos_urls, write_results
from youtube import make_search

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_INTERRUPTED = 130


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="am2yt",
        description="Turn a public Apple Music playlist into a YouTube playlist.",
    )
    parser.add_argument(
        "url", nargs="?", help="public Apple Music playlist URL"
    )
    parser.add_argument(
        "--open", action="store_true", help="open the playlist in a browser"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="re-resolve every track, ignoring previously cached matches",
    )
    parser.add_argument(
        "--set",
        nargs=2,
        action="append",
        metavar=("TITLE", "VIDEO"),
        help=(
            "replace the cached video for a track, e.g. "
            '--set "Pleura" https://youtu.be/kPJm7lYMjJs. Repeatable. '
            "Give a playlist URL too and the results file is rewritten."
        ),
    )
    parser.add_argument(
        "--forget",
        action="append",
        metavar="TITLE_OR_ID",
        help=(
            "drop a cached match by track title or Apple track ID, so the next run "
            "searches for it again. Repeatable."
        ),
    )
    args = parser.parse_args(argv)
    if not args.url and not args.set and not args.forget:
        parser.error(
            "give a playlist URL, or --set / --forget to edit cached matches"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.url:
        if args.forget:
            code = forget_matches(args.forget, cache.DEFAULT_PATH)
            if code != EXIT_OK:
                return code
        if args.set:
            return set_matches(args.set, cache.DEFAULT_PATH)
        return EXIT_OK
    return run(
        args.url,
        use_cache=not args.no_cache,
        open_browser=args.open,
        set_pairs=args.set,
        forget=args.forget,
    )


def _find(needle: str, entries: dict, show: Callable[..., None]) -> str | None:
    """The cache key a user's `--set` / `--forget` argument refers to.

    An exact key match wins, so an Apple track ID can never be shadowed by a
    track whose title happens to be the same digits. Otherwise the needle is a
    case-insensitive substring of the title. Reports and returns None when the
    needle matches nothing, or more than one track -- picking one of two
    plausible takes silently would hand back the version the user meant to
    replace.
    """
    needle = needle.strip()
    if needle in entries:
        return needle

    found = [
        key for key, entry in entries.items() if needle.lower() in entry.title.lower()
    ]
    if not found:
        show(f"No cached track matching {needle!r}.")
        return None
    if len(found) > 1:
        names = ", ".join(sorted(entries[key].title for key in found))
        show(f"{needle!r} matches several tracks: {names}. Be more specific.")
        return None
    return found[0]


def _no_cache(cache_path: Path, flag: str, show: Callable[..., None]) -> None:
    show(
        f"No cached matches in {cache_path}. Run the playlist first, then {flag} "
        "to change what it chose."
    )


def set_matches(
    pairs: list[list[str]],
    cache_path: Path | None = None,
    show: Callable[..., None] = print,
) -> int:
    """Point cached tracks at different videos. Returns the process exit code.

    All or nothing: every edit is validated before any is written, so a typo in
    the third `--set` cannot leave the cache half-updated.
    """
    cache_path = cache_path if cache_path is not None else cache.DEFAULT_PATH
    entries = cache.load(cache_path)

    if not entries:
        _no_cache(cache_path, "--set", show)
        return EXIT_FAIL

    edits = []
    failed = False
    for title, video in pairs:
        new_id = video_id(video)
        if not new_id:
            show(f"Not a video ID or YouTube link: {video!r}")
            failed = True
            continue

        key = _find(title, entries, show)
        if key is None:
            failed = True
        else:
            edits.append((key, new_id))

    if failed:
        show("Nothing changed.")
        return EXIT_FAIL

    for key, new_id in edits:
        before = entries[key]
        # The old runtime described the old video, so drop it rather than carry
        # a duration that is now a lie.
        entries[key] = replace(before, video_id=new_id, duration_s=None)
        show(f"{before.title} — {before.artist}: {before.video_id} -> {new_id}")

    cache.save(entries, cache_path)
    return EXIT_OK


def forget_matches(
    needles: list[str],
    cache_path: Path | None = None,
    show: Callable[..., None] = print,
) -> int:
    """Drop cached matches so the next run resolves them again.

    Takes a track title or an Apple track ID. All or nothing, like `set_matches`:
    one unrecognised name deletes nothing.
    """
    cache_path = cache_path if cache_path is not None else cache.DEFAULT_PATH
    entries = cache.load(cache_path)

    if not entries:
        _no_cache(cache_path, "--forget", show)
        return EXIT_FAIL

    keys = []
    failed = False
    for needle in needles:
        key = _find(needle, entries, show)
        if key is None:
            failed = True
        else:
            keys.append(key)

    if failed:
        show("Nothing changed.")
        return EXIT_FAIL

    for key in keys:
        gone = entries.pop(key)
        show(f"Forgot {gone.title} — {gone.artist} ({gone.video_id})")

    cache.save(entries, cache_path)
    return EXIT_OK


def run(
    url: str,
    *,
    search: Callable[[str], list] | None = None,
    cache_path: Path | None = None,
    use_cache: bool = True,
    directory: Path | None = None,
    open_browser: bool = False,
    set_pairs: list[list[str]] | None = None,
    forget: list[str] | None = None,
    ask: Callable[..., str] = input,
    show: Callable[..., None] = print,
) -> int:
    """Resolve a playlist end to end. Returns the process exit code."""
    cache_path = cache_path if cache_path is not None else cache.DEFAULT_PATH

    # Both edits land before the cache is read below, so a forgotten track is
    # re-resolved and a --set track is used as given, all in one command.
    if forget:
        code = forget_matches(forget, cache_path, show=show)
        if code != EXIT_OK:
            return code

    if set_pairs:
        code = set_matches(set_pairs, cache_path, show=show)
        if code != EXIT_OK:
            return code

    try:
        playlist = fetch_playlist(url)
    except AppleError as exc:
        show(f"Could not read the playlist: {exc}")
        return EXIT_FAIL

    if playlist.truncated:
        show(
            f"Warning: this playlist has {playlist.reported_total} songs but the page "
            f"only embeds {len(playlist.tracks)}. Continuing with those."
        )

    known = cache.load(cache_path) if use_cache else {}
    search = search if search is not None else make_search()

    results, interrupted = _resolve_all(playlist, known, search, ask, show)

    resolved = {
        result.track.apple_id: result.candidate for result in results if result.matched
    }
    cache.save({**known, **resolved} if use_cache else resolved, cache_path)

    urls = watch_videos_urls(
        [result.candidate.video_id for result in results if result.matched]
    )
    path = write_results(playlist.name, results, urls, directory)

    _report(playlist, results, urls, path, show)

    if open_browser and urls:
        webbrowser.open(urls[0])

    if interrupted:
        return EXIT_INTERRUPTED
    return EXIT_OK if urls else EXIT_FAIL


def _resolve_all(playlist, known, search, ask, show) -> tuple[list[Result], bool]:
    """Resolve each track in order. Returns the results and whether Ctrl-C hit."""
    results: list[Result] = []
    for position, track in enumerate(playlist.tracks, start=1):
        cached = known.get(track.apple_id)
        if cached:
            results.append(Result(track, cached, confident=True, from_cache=True))
            continue

        show(f"[{position}/{len(playlist.tracks)}] {track.title} — {track.artist}")
        try:
            decision = resolve(track, search, ask=ask, show=show)
        except KeyboardInterrupt:
            show("\nStopping. Saving what we have so far.")
            return results, True
        except Exception as exc:  # one bad track must not end the run
            show(f"  Search failed ({exc}). Skipping.")
            results.append(Result(track, None, confident=False))
            continue

        results.append(Result(track, decision.candidate, confident=decision.confident))
        if decision.stop:
            show("Stopping. Saving what we have so far.")
            break

    return results, False


def _report(playlist, results, urls, path, show) -> None:
    matched = [result for result in results if result.matched]
    from_cache = [result for result in matched if result.from_cache]
    unsure = [
        result for result in matched if not result.confident and not result.from_cache
    ]

    show("")
    show(
        f"{len(matched)} matched, {len(results) - len(matched)} skipped, "
        f"{len(from_cache)} from cache."
    )
    if unsure:
        show(f"{len(unsure)} match(es) you picked by hand are flagged in the file.")
    show(f"Wrote {path}")

    if not urls:
        show("Nothing matched, so there is no playlist to open.")
        return

    show("")
    for index, url in enumerate(urls, start=1):
        label = f"Playlist {index} of {len(urls)}" if len(urls) > 1 else "Playlist"
        show(f"{label}: {url}")
    show("")
    show("These playlists are temporary. Open one and click Save to keep it.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(EXIT_INTERRUPTED)
