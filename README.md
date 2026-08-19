# am2yt

Turn a public Apple Music playlist into a YouTube playlist. No login, no API
keys, no OAuth consent screen.

## Install

```bash
cd ~/Developer/am2yt
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Use

```bash
.venv/bin/python am2yt.py "https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb"
```

It scrapes the playlist, searches YouTube Music for each track, and asks you to
choose whenever the best match is not clearly correct:

```
? Man I Need — Olivia Dean [3:04]
  1. Man I Need — Olivia Dean — The Art of Loving [3:04] (+0s) score 100
  2. Man I Need — Matt Terry — Man I Need [3:05] (+1s) score 64
  pick 1-2, [s]kip, [m]anual search, [p]aste a link, [q]uit and save:
```

- a number picks that candidate
- `m` runs a different search
- `p` takes a video ID or link you found yourself — `05s4dEcAgMI`,
  `https://www.youtube.com/watch?v=05s4dEcAgMI`, and `https://youtu.be/05s4dEcAgMI`
  all work
- `s` skips the track, `q` stops and saves everything answered so far

If a search finds nothing at all you still get this prompt, so `p` and `m` are
always available.

At the end you get a `<playlist-name>.md` file listing every track and its match,
plus a playlist URL.

**The playlist is temporary until you save it.** Open the URL and click Save in
YouTube to keep it on your account.

### Flags

- `--open` — open the playlist in your browser when the run finishes
- `--no-cache` — re-resolve every track instead of reusing cached matches
- `--set "<title>" <video>` — point a track at a different video (see below)

## Fixing a bad match after the fact

The `.md` file is output only — it's regenerated every run, so editing it changes
nothing. Use `--set`, which rewrites the cached match:

```bash
.venv/bin/python am2yt.py --set "Pleura" https://youtu.be/kPJm7lYMjJs
```

- Titles match case-insensitively on a substring, so `--set "pleura"` works.
- Takes a bare ID or any YouTube link; `?si=` tracking params are stripped.
- Repeatable: `--set "Pleura" <id> --set "Rattlesnake" <id>`.
- Add the playlist URL to rewrite the `.md` and playlist link in the same command:
  ```bash
  .venv/bin/python am2yt.py "<playlist-url>" --set "Pleura" https://youtu.be/kPJm7lYMjJs
  ```
  Without a URL it just edits the cache and exits.

Edits are all-or-nothing — a typo in the third `--set` means none are written, so
the cache never ends up half-updated. An ambiguous title is refused rather than
guessed:

```
'Pleura' matches several tracks: Pleura, Pleura (Live). Be more specific.
Nothing changed.
```

To re-resolve a track from scratch instead (search + prompt again), delete its
entry from `~/.am2yt/cache.json` and rerun.

## How it works

| Step | Auth needed |
|---|---|
| Read the Apple Music playlist page | none — the page embeds its track list as JSON |
| Search YouTube Music | none — `ytmusicapi` works unauthenticated |
| Build the playlist | none — `watch_videos?video_ids=…` makes a temporary playlist |

Writing a *permanent* playlist to your account is the one thing that would need
credentials, so the tool hands you a temporary one and lets you click Save.

## Limits

- **50 tracks per run.** The Apple Music page embeds only the first 50. Longer
  playlists are truncated, with a warning naming both counts.
- `watch_videos` takes 50 IDs per URL, so runs over 50 matches produce several
  separate temporary playlists.
- Public playlist links only — not your personal library.

## Cache

Resolved matches are stored in `~/.am2yt/cache.json`, keyed by Apple's track ID.
Reruns skip both the search and the prompts, so if you lose a temporary playlist
before saving it, rerunning regenerates the URL instantly.

## Tests

```bash
.venv/bin/python -m pytest
```

No network access — the Apple parser runs against a captured page in
`tests/fixtures/`, and YouTube search is injected.
