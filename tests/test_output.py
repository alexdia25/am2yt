import pytest

from models import Candidate, Result, Track
from output import (
    CHUNK_SIZE,
    results_markdown,
    slugify,
    watch_videos_urls,
    write_results,
)

TRACK = Track("1817609509", "Man I Need", "Olivia Dean", "The Art of Loving", 184000)
OTHER = Track("1820918468", "Rein Me In", "Sam Fender", "Rein Me In - Single", 340000)
EXACT = Candidate("fsGjRf-N71I", "Man I Need", "Olivia Dean", "The Art of Loving", 184)
COVER = Candidate("YG7WEnYSpZI", "Man I Need", "Matt Terry", "Man I Need", 185)


def ids(count):
    return [f"v{index:03d}" for index in range(count)]


def test_one_url_for_a_single_id():
    urls = watch_videos_urls(["fsGjRf-N71I"])
    assert urls == ["https://www.youtube.com/watch_videos?video_ids=fsGjRf-N71I"]


def test_ids_are_comma_separated():
    assert watch_videos_urls(["a", "b", "c"])[0].endswith("video_ids=a,b,c")


def test_no_ids_gives_no_urls():
    assert watch_videos_urls([]) == []


def test_exactly_fifty_ids_is_one_url():
    assert len(watch_videos_urls(ids(CHUNK_SIZE))) == 1


def test_forty_nine_ids_is_one_url():
    assert len(watch_videos_urls(ids(49))) == 1


def test_fifty_one_ids_is_two_urls():
    urls = watch_videos_urls(ids(51))
    assert len(urls) == 2
    assert urls[0].count(",") == CHUNK_SIZE - 1
    assert urls[1].endswith("video_ids=v050")


def test_chunking_loses_no_ids():
    every = ids(137)
    joined = ",".join(url.split("video_ids=")[1] for url in watch_videos_urls(every))
    assert joined.split(",") == every


def test_slugify_lowercases_and_dashes():
    assert slugify("Today's Hits") == "todays-hits"


def test_slugify_strips_the_curly_apostrophe_apple_actually_uses():
    assert slugify("Today’s Hits") == "todays-hits"


def test_slugify_collapses_runs_of_separators():
    assert slugify("  A -- B / C  ") == "a-b-c"


def test_slugify_falls_back_when_nothing_survives():
    assert slugify("!!!") == "playlist"


def test_markdown_lists_a_match_with_its_link():
    text = results_markdown("Today's Hits", [Result(TRACK, EXACT, True)], [])
    assert "Today's Hits" in text
    assert "Man I Need" in text
    assert "https://www.youtube.com/watch?v=fsGjRf-N71I" in text
    assert "3:04" in text


def test_markdown_flags_a_low_confidence_match():
    confident = results_markdown("P", [Result(TRACK, EXACT, True)], [])
    unsure = results_markdown("P", [Result(TRACK, COVER, False)], [])
    assert "low confidence" in unsure
    assert "low confidence" not in confident


def test_markdown_does_not_flag_a_cached_match():
    text = results_markdown("P", [Result(TRACK, EXACT, False, from_cache=True)], [])
    assert "low confidence" not in text
    assert "cached" in text


def test_markdown_marks_a_skipped_track():
    text = results_markdown("P", [Result(OTHER, None, False)], [])
    assert "Rein Me In" in text
    assert "no match" in text


def test_markdown_keeps_playlist_order_including_skips():
    text = results_markdown(
        "P", [Result(TRACK, EXACT, True), Result(OTHER, None, False)], []
    )
    assert text.index("Man I Need") < text.index("Rein Me In")
    assert "1." in text and "2." in text


def test_markdown_counts_matched_and_skipped():
    text = results_markdown(
        "P", [Result(TRACK, EXACT, True), Result(OTHER, None, False)], []
    )
    assert "1 matched" in text
    assert "1 skipped" in text


def test_markdown_includes_the_urls_and_the_save_reminder():
    url = "https://www.youtube.com/watch_videos?video_ids=fsGjRf-N71I"
    text = results_markdown("P", [Result(TRACK, EXACT, True)], [url])
    assert url in text
    assert "Save" in text


def test_markdown_numbers_multiple_urls():
    text = results_markdown("P", [], ["url-one", "url-two"])
    assert "1 of 2" in text
    assert "2 of 2" in text


def test_write_results_uses_the_slug_as_the_filename(tmp_path):
    path = write_results("Today’s Hits", [Result(TRACK, EXACT, True)], [], tmp_path)
    assert path == tmp_path / "todays-hits.md"
    assert "Man I Need" in path.read_text(encoding="utf-8")
