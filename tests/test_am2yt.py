from pathlib import Path

import pytest

import am2yt
import cache
from apple import AppleFetchError, Playlist
from models import Candidate, Track

TRACK_A = Track("1817609509", "Man I Need", "Olivia Dean", "The Art of Loving", 184000)
TRACK_B = Track("1820918468", "Rein Me In", "Sam Fender", "Rein Me In - Single", 340000)

MATCH_A = Candidate("fsGjRf-N71I", "Man I Need", "Olivia Dean", "The Art of Loving", 184)
MATCH_B = Candidate("NO3JTAsB4NI", "Rein Me In", "Sam Fender, Olivia Dean", None, 340)

PLAYLIST = Playlist(name="Today's Hits", tracks=[TRACK_A, TRACK_B], reported_total=2)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "cache.json", tmp_path / "out"


@pytest.fixture(autouse=True)
def out_dir(paths):
    paths[1].mkdir(parents=True, exist_ok=True)
    return paths[1]


@pytest.fixture
def fetched(monkeypatch):
    """Stub the Apple scrape. Tests set .playlist or .error."""

    class Stub:
        playlist = PLAYLIST
        error = None

        def __call__(self, url):
            if self.error:
                raise self.error
            return self.playlist

    stub = Stub()
    monkeypatch.setattr(am2yt, "fetch_playlist", stub)
    return stub


def searcher(by_query):
    def search(query):
        return by_query.get(query, [])

    return search


BOTH_FOUND = {
    "Man I Need Olivia Dean": [MATCH_A],
    "Rein Me In Sam Fender": [MATCH_B],
}


def run(paths, **kwargs):
    cache_path, directory = paths
    defaults = dict(
        search=searcher(BOTH_FOUND),
        cache_path=cache_path,
        directory=directory,
        ask=lambda *_: "s",
        show=lambda *_: None,
    )
    return am2yt.run("https://music.apple.com/us/playlist/x/pl.1", **{**defaults, **kwargs})


def read_output(directory) -> str:
    files = list(Path(directory).glob("*.md"))
    assert len(files) == 1, f"expected one results file, got {files}"
    return files[0].read_text(encoding="utf-8")


def test_matches_every_track_and_succeeds(fetched, paths):
    assert run(paths) == 0
    text = read_output(paths[1])
    assert "2 matched, 0 skipped" in text


def test_writes_the_playlist_url(fetched, paths):
    run(paths)
    text = read_output(paths[1])
    assert "video_ids=fsGjRf-N71I,NO3JTAsB4NI" in text


def test_caches_what_it_resolved(fetched, paths):
    run(paths)
    assert cache.load(paths[0]) == {TRACK_A.apple_id: MATCH_A, TRACK_B.apple_id: MATCH_B}


def test_a_cache_hit_skips_searching(fetched, paths):
    cache.save({TRACK_A.apple_id: MATCH_A}, paths[0])
    queried = []

    def search(query):
        queried.append(query)
        return BOTH_FOUND.get(query, [])

    assert run(paths, search=search) == 0
    assert queried == ["Rein Me In Sam Fender"]
    assert "cached" in read_output(paths[1])


def test_no_cache_flag_searches_everything_again(fetched, paths):
    cache.save({TRACK_A.apple_id: MATCH_A}, paths[0])
    queried = []

    def search(query):
        queried.append(query)
        return BOTH_FOUND.get(query, [])

    run(paths, search=search, use_cache=False)
    assert len(queried) == 2


def test_a_track_with_no_results_is_skipped_but_the_run_succeeds(fetched, paths):
    assert run(paths, search=searcher({"Man I Need Olivia Dean": [MATCH_A]})) == 0
    text = read_output(paths[1])
    assert "1 matched, 1 skipped" in text
    assert "no match" in text


def test_a_search_error_skips_that_track_and_keeps_going(fetched, paths):
    def search(query):
        if query == "Man I Need Olivia Dean":
            raise RuntimeError("network gone")
        return BOTH_FOUND[query]

    assert run(paths, search=search) == 0
    text = read_output(paths[1])
    assert "1 matched, 1 skipped" in text


def test_zero_matches_writes_a_file_and_fails(fetched, paths):
    assert run(paths, search=searcher({})) == 1
    text = read_output(paths[1])
    assert "0 matched, 2 skipped" in text
    assert "video_ids=" not in text


def test_an_apple_failure_reports_and_fails(fetched, paths):
    fetched.error = AppleFetchError("boom")
    shown = []
    assert run(paths, show=shown.append) == 1
    assert any("boom" in str(line) for line in shown)


def test_a_truncated_playlist_warns_and_continues(fetched, paths):
    fetched.playlist = Playlist(name="Big", tracks=[TRACK_A], reported_total=120)
    shown = []
    assert run(paths, show=shown.append) == 0
    text = " ".join(str(line) for line in shown)
    assert "120" in text
    assert "1" in text


def test_quitting_at_a_prompt_saves_progress_so_far(fetched, paths):
    ambiguous = {
        "Man I Need Olivia Dean": [MATCH_A],
        "Rein Me In Sam Fender": [
            MATCH_B,
            Candidate("dup", "Rein Me In", "Sam Fender", None, 340),
        ],
    }
    assert run(paths, search=searcher(ambiguous), ask=lambda *_: "q") == 0
    assert cache.load(paths[0]) == {TRACK_A.apple_id: MATCH_A}
    assert "1 matched, 1 skipped" in read_output(paths[1])


def test_ctrl_c_mid_run_still_saves_progress(fetched, paths):
    def search(query):
        if query == "Rein Me In Sam Fender":
            raise KeyboardInterrupt
        return BOTH_FOUND[query]

    assert run(paths, search=search) == 130
    assert cache.load(paths[0]) == {TRACK_A.apple_id: MATCH_A}
    assert "1 matched" in read_output(paths[1])


def test_open_browser_opens_the_first_url(fetched, paths, monkeypatch):
    opened = []
    monkeypatch.setattr(am2yt.webbrowser, "open", lambda url: opened.append(url))
    run(paths, open_browser=True)
    assert len(opened) == 1
    assert "video_ids=" in opened[0]


def test_open_browser_opens_nothing_when_nothing_matched(fetched, paths, monkeypatch):
    opened = []
    monkeypatch.setattr(am2yt.webbrowser, "open", lambda url: opened.append(url))
    run(paths, search=searcher({}), open_browser=True)
    assert opened == []


def test_no_browser_is_opened_by_default(fetched, paths, monkeypatch):
    opened = []
    monkeypatch.setattr(am2yt.webbrowser, "open", lambda url: opened.append(url))
    run(paths)
    assert opened == []


def test_main_requires_a_url():
    with pytest.raises(SystemExit):
        am2yt.main([])


def test_main_parses_the_flags():
    args = am2yt.parse_args(["https://music.apple.com/x", "--open", "--no-cache"])
    assert args.url == "https://music.apple.com/x"
    assert args.open is True
    assert args.no_cache is True
