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


def test_a_pasted_link_reaches_the_playlist_and_the_cache(fetched, paths):
    """Search finds nothing for track B, so the user supplies the video by hand."""
    answers = iter(["p", "05s4dEcAgMI"])

    assert (
        run(
            paths,
            search=searcher({"Man I Need Olivia Dean": [MATCH_A]}),
            ask=lambda *_: next(answers),
        )
        == 0
    )
    text = read_output(paths[1])
    assert "2 matched, 0 skipped" in text
    assert "video_ids=fsGjRf-N71I,05s4dEcAgMI" in text
    assert cache.load(paths[0])[TRACK_B.apple_id].video_id == "05s4dEcAgMI"


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


def test_main_requires_a_url_or_a_set():
    with pytest.raises(SystemExit):
        am2yt.main([])


def test_main_parses_the_flags():
    args = am2yt.parse_args(["https://music.apple.com/x", "--open", "--no-cache"])
    assert args.url == "https://music.apple.com/x"
    assert args.open is True
    assert args.no_cache is True


def test_main_parses_repeated_sets_without_a_url():
    args = am2yt.parse_args(
        ["--set", "Pleura", "https://youtu.be/kPJm7lYMjJs", "--set", "Rattlesnake", "abc"]
    )
    assert args.url is None
    assert args.set == [
        ["Pleura", "https://youtu.be/kPJm7lYMjJs"],
        ["Rattlesnake", "abc"],
    ]


# --- set_matches -------------------------------------------------------------


def stored(cache_path):
    return {entry.title: entry.video_id for entry in cache.load(cache_path).values()}


@pytest.fixture
def stocked(paths):
    """A cache holding both tracks, as a finished run would leave it."""
    cache.save({TRACK_A.apple_id: MATCH_A, TRACK_B.apple_id: MATCH_B}, paths[0])
    return paths[0]


def test_set_overwrites_the_video_id(stocked):
    assert am2yt.set_matches(
        [["Man I Need", "https://youtu.be/05s4dEcAgMI"]], stocked, show=lambda *_: None
    ) == 0
    assert stored(stocked)["Man I Need"] == "05s4dEcAgMI"


def test_set_keeps_the_other_entries_untouched(stocked):
    am2yt.set_matches([["Man I Need", "05s4dEcAgMI"]], stocked, show=lambda *_: None)
    entries = cache.load(stocked)
    assert len(entries) == 2
    assert entries[TRACK_B.apple_id] == MATCH_B


def test_set_keeps_the_title_and_artist(stocked):
    """Only the video changes -- the labels still describe the Apple track."""
    am2yt.set_matches([["Man I Need", "05s4dEcAgMI"]], stocked, show=lambda *_: None)
    entry = cache.load(stocked)[TRACK_A.apple_id]
    assert entry.title == MATCH_A.title
    assert entry.artist == MATCH_A.artist


def test_set_clears_the_stale_duration(stocked):
    """The old runtime described the old video, so it must not be kept."""
    am2yt.set_matches([["Man I Need", "05s4dEcAgMI"]], stocked, show=lambda *_: None)
    assert cache.load(stocked)[TRACK_A.apple_id].duration_s is None


def test_set_matches_a_title_case_insensitively(stocked):
    assert am2yt.set_matches(
        [["man i need", "05s4dEcAgMI"]], stocked, show=lambda *_: None
    ) == 0
    assert stored(stocked)["Man I Need"] == "05s4dEcAgMI"


def test_set_matches_on_a_partial_title(stocked):
    assert am2yt.set_matches([["rein me", "05s4dEcAgMI"]], stocked, show=lambda *_: None) == 0
    assert stored(stocked)["Rein Me In"] == "05s4dEcAgMI"


def test_set_accepts_a_full_url_with_tracking_params(stocked):
    am2yt.set_matches(
        [["Man I Need", "https://youtu.be/05s4dEcAgMI?si=eOW5PlXv9sSlgBVl"]],
        stocked,
        show=lambda *_: None,
    )
    assert stored(stocked)["Man I Need"] == "05s4dEcAgMI"


def test_set_applies_several_edits_at_once(stocked):
    assert am2yt.set_matches(
        [["Man I Need", "05s4dEcAgMI"], ["Rein Me In", "Q-i1XZc8ZwA"]],
        stocked,
        show=lambda *_: None,
    ) == 0
    assert stored(stocked) == {"Man I Need": "05s4dEcAgMI", "Rein Me In": "Q-i1XZc8ZwA"}


def test_set_refuses_an_ambiguous_title_and_changes_nothing(paths):
    """A studio cut and a live cut both match "Pleura" -- guess wrong and the
    user silently gets the take they were trying to replace."""
    studio = Candidate("aaaaaaaaaaa", "Pleura", "King Gizzard", "L.W.", 252)
    live = Candidate("bbbbbbbbbbb", "Pleura (Live)", "King Gizzard", "Live", 300)
    cache.save({"1": studio, "2": live}, paths[0])

    shown = []
    assert am2yt.set_matches([["Pleura", "05s4dEcAgMI"]], paths[0], show=shown.append) == 1
    assert stored(paths[0]) == {"Pleura": "aaaaaaaaaaa", "Pleura (Live)": "bbbbbbbbbbb"}
    text = " ".join(str(line) for line in shown)
    assert "Pleura" in text and "Pleura (Live)" in text


def test_set_can_still_target_one_of_two_similar_titles(paths):
    """The escape hatch from ambiguity: type more of the title."""
    studio = Candidate("aaaaaaaaaaa", "Pleura", "King Gizzard", "L.W.", 252)
    live = Candidate("bbbbbbbbbbb", "Pleura (Live)", "King Gizzard", "Live", 300)
    cache.save({"1": studio, "2": live}, paths[0])

    assert am2yt.set_matches(
        [["Pleura (Live)", "05s4dEcAgMI"]], paths[0], show=lambda *_: None
    ) == 0
    assert stored(paths[0]) == {"Pleura": "aaaaaaaaaaa", "Pleura (Live)": "05s4dEcAgMI"}


def test_set_reports_a_title_it_cannot_find(stocked):
    shown = []
    assert am2yt.set_matches([["Nonexistent", "05s4dEcAgMI"]], stocked, show=shown.append) == 1
    assert any("Nonexistent" in str(line) for line in shown)


def test_set_rejects_a_link_with_no_video_id(stocked):
    shown = []
    assert am2yt.set_matches([["Man I Need", "not a link"]], stocked, show=shown.append) == 1
    assert stored(stocked)["Man I Need"] == MATCH_A.video_id
    assert any("not a link" in str(line) for line in shown)


def test_one_bad_edit_blocks_every_edit(stocked):
    """All-or-nothing: a typo must not leave the cache half-updated."""
    assert am2yt.set_matches(
        [["Man I Need", "05s4dEcAgMI"], ["Nonexistent", "Q-i1XZc8ZwA"]],
        stocked,
        show=lambda *_: None,
    ) == 1
    assert stored(stocked)["Man I Need"] == MATCH_A.video_id


def test_set_on_an_empty_cache_explains_itself(paths):
    shown = []
    assert am2yt.set_matches([["Pleura", "05s4dEcAgMI"]], paths[0], show=shown.append) == 1
    assert any("cache" in str(line).lower() for line in shown)


def test_set_reports_what_it_changed(stocked):
    shown = []
    am2yt.set_matches([["Man I Need", "05s4dEcAgMI"]], stocked, show=shown.append)
    text = " ".join(str(line) for line in shown)
    assert "Man I Need" in text
    assert MATCH_A.video_id in text
    assert "05s4dEcAgMI" in text


# --- forget_matches ----------------------------------------------------------


def test_forget_deletes_by_title(stocked):
    assert am2yt.forget_matches(["Man I Need"], stocked, show=lambda *_: None) == 0
    assert set(cache.load(stocked)) == {TRACK_B.apple_id}


def test_forget_deletes_by_apple_id(stocked):
    assert am2yt.forget_matches([TRACK_A.apple_id], stocked, show=lambda *_: None) == 0
    assert set(cache.load(stocked)) == {TRACK_B.apple_id}


def test_forget_matches_a_title_case_insensitively(stocked):
    assert am2yt.forget_matches(["man i need"], stocked, show=lambda *_: None) == 0
    assert set(cache.load(stocked)) == {TRACK_B.apple_id}


def test_forget_matches_on_a_partial_title(stocked):
    assert am2yt.forget_matches(["rein me"], stocked, show=lambda *_: None) == 0
    assert set(cache.load(stocked)) == {TRACK_A.apple_id}


def test_forget_deletes_several_at_once(stocked):
    assert am2yt.forget_matches(
        ["Man I Need", TRACK_B.apple_id], stocked, show=lambda *_: None
    ) == 0
    assert cache.load(stocked) == {}


def test_an_id_that_looks_like_a_title_still_deletes_by_id(paths):
    """An exact key match wins, so a numeric title cannot shadow an ID."""
    numeric = Candidate("aaaaaaaaaaa", "1832806846", "Whoever", None, 100)
    target = Candidate("bbbbbbbbbbb", "Pleura", "King Gizzard", None, 252)
    cache.save({"1832806846": target, "999": numeric}, paths[0])

    assert am2yt.forget_matches(["1832806846"], paths[0], show=lambda *_: None) == 0
    assert set(cache.load(paths[0])) == {"999"}


def test_forget_refuses_an_ambiguous_title_and_deletes_nothing(paths):
    studio = Candidate("aaaaaaaaaaa", "Pleura", "King Gizzard", "L.W.", 252)
    live = Candidate("bbbbbbbbbbb", "Pleura (Live)", "King Gizzard", "Live", 300)
    cache.save({"1": studio, "2": live}, paths[0])

    shown = []
    assert am2yt.forget_matches(["Pleura"], paths[0], show=shown.append) == 1
    assert set(cache.load(paths[0])) == {"1", "2"}
    text = " ".join(str(line) for line in shown)
    assert "Pleura" in text and "Pleura (Live)" in text


def test_forget_reports_a_title_it_cannot_find(stocked):
    shown = []
    assert am2yt.forget_matches(["Nonexistent"], stocked, show=shown.append) == 1
    assert any("Nonexistent" in str(line) for line in shown)
    assert len(cache.load(stocked)) == 2


def test_one_bad_forget_blocks_every_forget(stocked):
    """All-or-nothing, same as --set."""
    assert am2yt.forget_matches(
        ["Man I Need", "Nonexistent"], stocked, show=lambda *_: None
    ) == 1
    assert len(cache.load(stocked)) == 2


def test_forget_on_an_empty_cache_explains_itself(paths):
    shown = []
    assert am2yt.forget_matches(["Pleura"], paths[0], show=shown.append) == 1
    assert any("cache" in str(line).lower() for line in shown)


def test_forget_reports_what_it_deleted(stocked):
    shown = []
    am2yt.forget_matches(["Man I Need"], stocked, show=shown.append)
    text = " ".join(str(line) for line in shown)
    assert "Man I Need" in text
    assert MATCH_A.video_id in text


def test_forgetting_everything_leaves_a_readable_empty_cache(stocked):
    am2yt.forget_matches(
        ["Man I Need", "Rein Me In"], stocked, show=lambda *_: None
    )
    assert cache.load(stocked) == {}


# --- --set through main ------------------------------------------------------


def test_set_without_a_url_only_edits(fetched, paths, monkeypatch):
    cache.save({TRACK_A.apple_id: MATCH_A}, paths[0])
    monkeypatch.setattr(am2yt.cache, "DEFAULT_PATH", paths[0])
    assert am2yt.main(["--set", "Man I Need", "05s4dEcAgMI"]) == 0
    assert stored(paths[0])["Man I Need"] == "05s4dEcAgMI"
    assert list(Path(paths[1]).glob("*.md")) == []


def test_set_with_a_url_edits_then_reruns(fetched, paths):
    cache.save({TRACK_A.apple_id: MATCH_A, TRACK_B.apple_id: MATCH_B}, paths[0])
    assert run(paths, set_pairs=[["Man I Need", "05s4dEcAgMI"]]) == 0
    text = read_output(paths[1])
    assert "video_ids=05s4dEcAgMI,NO3JTAsB4NI" in text


def test_a_failed_set_stops_the_run(fetched, paths):
    cache.save({TRACK_A.apple_id: MATCH_A}, paths[0])
    assert run(paths, set_pairs=[["Nonexistent", "05s4dEcAgMI"]]) == 1
    assert list(Path(paths[1]).glob("*.md")) == []


def test_main_parses_repeated_forgets():
    args = am2yt.parse_args(["--forget", "Pleura", "--forget", "1832806846"])
    assert args.url is None
    assert args.forget == ["Pleura", "1832806846"]


def test_forget_without_a_url_only_edits(fetched, paths, monkeypatch):
    cache.save({TRACK_A.apple_id: MATCH_A}, paths[0])
    monkeypatch.setattr(am2yt.cache, "DEFAULT_PATH", paths[0])
    assert am2yt.main(["--forget", "Man I Need"]) == 0
    assert cache.load(paths[0]) == {}
    assert list(Path(paths[1]).glob("*.md")) == []


def test_forget_with_a_url_re_resolves_that_track(fetched, paths):
    """The point of forgetting: the next run searches for it again."""
    stale = Candidate("staleeeeeee", "Man I Need", "Olivia Dean", None, 184)
    cache.save({TRACK_A.apple_id: stale, TRACK_B.apple_id: MATCH_B}, paths[0])

    queried = []

    def search(query):
        queried.append(query)
        return BOTH_FOUND.get(query, [])

    assert run(paths, search=search, forget=["Man I Need"]) == 0
    assert queried == ["Man I Need Olivia Dean"]
    assert cache.load(paths[0])[TRACK_A.apple_id].video_id == MATCH_A.video_id
    assert f"video_ids={MATCH_A.video_id},{MATCH_B.video_id}" in read_output(paths[1])


def test_a_failed_forget_stops_the_run(fetched, paths):
    cache.save({TRACK_A.apple_id: MATCH_A}, paths[0])
    assert run(paths, forget=["Nonexistent"]) == 1
    assert list(Path(paths[1]).glob("*.md")) == []


def test_forget_and_set_can_be_combined(fetched, paths):
    cache.save({TRACK_A.apple_id: MATCH_A, TRACK_B.apple_id: MATCH_B}, paths[0])
    assert (
        run(
            paths,
            forget=["Man I Need"],
            set_pairs=[["Rein Me In", "05s4dEcAgMI"]],
        )
        == 0
    )
    entries = cache.load(paths[0])
    assert entries[TRACK_A.apple_id].video_id == MATCH_A.video_id  # re-resolved
    assert entries[TRACK_B.apple_id].video_id == "05s4dEcAgMI"  # set
