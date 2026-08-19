import json

import pytest

import cache
from models import Candidate

EXACT = Candidate("fsGjRf-N71I", "Man I Need", "Olivia Dean", "The Art of Loving", 184)
NO_ALBUM = Candidate("abc", "Rein Me In", "Sam Fender", None, None)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "nested" / "cache.json"


def test_round_trips_entries(path):
    cache.save({"1817609509": EXACT, "2": NO_ALBUM}, path)
    assert cache.load(path) == {"1817609509": EXACT, "2": NO_ALBUM}


def test_creates_missing_parent_directories(path):
    cache.save({"1": EXACT}, path)
    assert path.exists()


def test_missing_file_loads_as_empty(path):
    assert cache.load(path) == {}


def test_corrupt_json_loads_as_empty(path):
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert cache.load(path) == {}


def test_non_object_json_loads_as_empty(path):
    path.parent.mkdir(parents=True)
    path.write_text('["nope"]', encoding="utf-8")
    assert cache.load(path) == {}


def test_malformed_entries_are_dropped_and_good_ones_kept(path):
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "good": {
                    "video_id": "fsGjRf-N71I",
                    "title": "Man I Need",
                    "artist": "Olivia Dean",
                    "album": "The Art of Loving",
                    "duration_s": 184,
                },
                "no_video_id": {"title": "X", "artist": "Y"},
                "not_a_dict": "nope",
                "unknown_field": {
                    "video_id": "v2",
                    "title": "T",
                    "artist": "A",
                    "surprise": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = cache.load(path)
    assert set(loaded) == {"good", "unknown_field"}
    assert loaded["good"] == EXACT
    assert loaded["unknown_field"].video_id == "v2"


def test_save_overwrites_previous_contents(path):
    cache.save({"1": EXACT}, path)
    cache.save({"2": NO_ALBUM}, path)
    assert set(cache.load(path)) == {"2"}


def test_saved_file_is_readable_json(path):
    cache.save({"1": EXACT}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["1"]["video_id"] == EXACT.video_id


def test_default_path_is_under_the_home_directory():
    assert cache.DEFAULT_PATH.name == "cache.json"
    assert ".am2yt" in cache.DEFAULT_PATH.parts
