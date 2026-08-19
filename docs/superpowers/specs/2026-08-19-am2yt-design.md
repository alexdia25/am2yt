# am2yt — Apple Music playlist → YouTube playlist

**Date:** 2026-08-19
**Status:** Approved, ready for implementation plan

## Purpose

Take a link to a public Apple Music playlist and produce a YouTube playlist of the
same songs. Personal CLI tool. Runs on demand, on one machine.

## Constraints

- **No authentication anywhere.** No Google Cloud project, no OAuth consent screen,
  no YouTube cookies on disk. This is the defining constraint and it shapes the
  output format (see Output below).
- **Accuracy over speed.** The tool asks the user when a match is uncertain rather
  than silently guessing. A wrong track in the playlist is worse than a prompt.
- **50 tracks per run is acceptable.** The Apple Music page embeds only the first 50
  tracks; longer playlists are truncated with a warning. Pagination is explicitly
  out of scope.
- Lives outside the Lyrebird `app` repo at `~/Developer/am2yt/` with its own venv.

## Verified Findings

These were confirmed against live services on 2026-08-19 before the design was
settled. They are the load-bearing assumptions.

1. **Apple Music public playlist pages are scrapable without auth.** A plain GET
   with a browser User-Agent returns HTML containing
   `<script id="serialized-server-data">` with a JSON payload. Tracks live under
   `data[0].data.sections`, in the section where `itemKind == "trackLockup"`. Each
   item carries title, artist, album, and duration in milliseconds.
2. **Only the first 50 tracks are embedded.** A separate footer section
   (`itemKind == "containerDetailTracklistFooterLockup"`) has a `description` field
   like `"50 songs, 2 hours 44 minutes"`, giving the true total to compare against.
3. **YouTube Music search works unauthenticated.** `YTMusic()` with no arguments —
   `search(query, filter="songs")` returns `videoId`, `title`, `artists`, `album`,
   and `duration_seconds`. Music-native results, so the correct studio track
   generally ranks first, with remixes and covers below it.
4. **`watch_videos` creates a temporary playlist without auth.** A GET to
   `https://www.youtube.com/watch_videos?video_ids=<comma-separated>` returns
   `303` with a `Location` header containing `list=TL…`. Loading that playlist URL
   confirmed all submitted videos are present. The playlist is ephemeral until the
   user clicks Save in the YouTube UI.

The `watch_videos` limit is 50 video IDs per URL. This happens to align with the
Apple Music 50-track page limit, so a typical run produces exactly one URL.

## Architecture

```
am2yt/
  am2yt.py          # CLI entry: arg parsing, orchestration
  apple.py          # scrape public playlist -> [Track]
  youtube.py        # unauthenticated YTMusic search -> [Candidate]
  matching.py       # candidate scoring + interactive picker
  cache.py          # resolved-match JSON store
  output.py         # results file + watch_videos URLs
  requirements.txt  # ytmusicapi, rapidfuzz, requests
  README.md
  tests/
    fixtures/todays-hits.html   # real page capture, for offline parser tests
```

Modules communicate only through two dataclasses. No module imports another's
internals.

```python
@dataclass(frozen=True)
class Track:            # one Apple Music song
    apple_id: str       # storeAdamID, the cache key
    title: str
    artist: str
    album: str | None
    duration_ms: int | None

@dataclass(frozen=True)
class Candidate:        # one YouTube Music search result
    video_id: str
    title: str
    artist: str
    album: str | None
    duration_s: int | None
```

Each module's contract:

| Module | Does | Depends on |
|---|---|---|
| `apple.py` | URL → `list[Track]`, plus reported total for the truncation warning | `requests` |
| `youtube.py` | query string → `list[Candidate]` | `ytmusicapi` |
| `matching.py` | `Track` + candidates → chosen `video_id` or skip | `rapidfuzz` |
| `cache.py` | `apple_id` ↔ `video_id` persistence | stdlib |
| `output.py` | results → file on disk + `watch_videos` URLs | stdlib |
| `am2yt.py` | sequences the above, owns all user-facing printing | all of the above |

## Data Flow

1. **Scrape.** `apple.py` GETs the playlist URL with a browser User-Agent, extracts
   the `serialized-server-data` script tag by regex, JSON-parses it, and walks
   sections for `itemKind == "trackLockup"`. Artist comes from
   `subtitleLinks[0].title`, album from `tertiaryLinks[0].title`, duration from
   `duration`, id from `contentDescriptor.identifiers.storeAdamID`. The playlist
   name comes from the header section. It also parses the leading integer out of the
   footer `description` string; if that number exceeds the tracks parsed, the run
   prints a warning naming both counts and continues with what it has.
2. **Cache lookup.** `cache.py` loads `~/.am2yt/cache.json`, keyed by `apple_id`. A
   hit supplies the `video_id` directly — no search, no prompt. This makes reruns
   cheap and lets the user regenerate a `watch_videos` URL instantly if they lost
   the temp playlist before saving.
3. **Search.** For each cache miss, `youtube.py` runs
   `search(f"{title} {artist}", filter="songs", limit=5)`.
4. **Match.** `matching.py` scores each candidate:
   - title similarity via `rapidfuzz.fuzz.token_set_ratio`
   - artist similarity via the same
   - duration penalty, scaled by `abs(candidate_s * 1000 - track_ms)`
   A candidate is auto-accepted only when its score clears the confidence threshold
   **and** leads the runner-up by a clear margin. Otherwise the picker prints the
   top 5 — numbered, each with artist, album, duration, and duration delta from the
   Apple track — and reads a choice: a number to pick, `s` to skip, `m` to type a
   replacement search query, `p` to paste a video ID or YouTube link directly, `q` to
   stop and save progress. A search returning nothing still prompts, because `p` and
   `m` are exactly what a user needs at that moment; the pasted video is labelled
   with the Apple track's own title and artist, since fetching its real metadata
   would cost a network round trip to show what the user already knows.
5. **Output.** `output.py` writes `<playlist-name>.md` in the current directory: one
   line per track showing the Apple title and artist, the matched YouTube title,
   artist, duration, and `watch?v=` link. Skipped tracks appear in the same file,
   explicitly marked, in playlist position order so they are easy to fix by hand. It
   then emits `watch_videos` URLs chunked at 50 IDs — one URL in the normal case,
   numbered chunks otherwise with a note that each chunk is a separate temp playlist.
6. **Finish.** `am2yt.py` writes the cache, prints the counts (added, skipped, cache
   hits), the URL(s), and the reminder that the playlist is temporary until saved in
   the YouTube UI.
7. **Correcting a match.** The results file is output only — regenerated every run —
   so `--set "<title>" <video>` edits the cache instead, matching the title
   case-insensitively on a substring and accepting a bare ID or any YouTube link.
   Edits are validated before any is written, so a typo cannot half-update the
   cache, and an ambiguous title is refused rather than guessed: picking one of two
   plausible takes silently would hand the user back the version they were trying
   to replace. The stale `duration_s` is cleared, since it described the old video.
   With a playlist URL the edit is followed by a normal run so the results file and
   playlist link are rewritten in one command; without one it edits and exits.

## CLI

```
am2yt.py <apple-music-playlist-url> [--open] [--no-cache]
```

- `--open` opens the first `watch_videos` URL with `webbrowser.open`.
- `--no-cache` ignores and overwrites cached matches for this run.

No non-interactive flag. The tool always prompts on uncertainty; that is the point.

## Error Handling

- **Apple fetch or parse failure** — hard fail. Print the URL and what broke.
  Nothing downstream is meaningful without the track list. A parse failure most
  likely means Apple changed the page shape, so the message says so.
- **Per-track search failure** — log it, treat that track as skipped, continue. One
  bad track never kills a run.
- **`Ctrl-C`** — flush the cache before exiting, so answered prompts are not lost.
- **Zero matches overall** — write the file listing every track as unmatched, print
  no `watch_videos` URL, exit non-zero.

## Testing

No network in tests.

- `apple.py` — parse `tests/fixtures/todays-hits.html` (a real capture). Assert 50
  tracks, and assert exact field values for the first track. Assert the truncation
  warning fires when the footer count exceeds the parsed count.
- `matching.py` — hand-built candidate sets covering the traps seen in real search
  output: exact match ranked first, a remix with a wildly different duration, a live
  version, and a same-title cover by a different artist. Assert auto-accept fires
  for the clean case and the picker is invoked for each trap. Picker input is
  injected, so `s`, `m`, `q`, and an out-of-range number are all testable.
- `output.py` — chunking at 49, 50, and 51 IDs. Assert one URL at 50, two at 51.
- `cache.py` — round-trip, and a corrupt cache file degrades to empty rather than
  crashing.
- `am2yt.py` — orchestration with `youtube.py` stubbed, asserting cache hits skip
  search entirely.

## Out of Scope

- Playlists over 50 tracks (warned, truncated).
- Writing to a YouTube account, which is what would require auth.
- Apple Music private or library playlists — public links only.
- Spotify or any other source.
