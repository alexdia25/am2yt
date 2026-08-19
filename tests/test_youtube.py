import pytest

from models import Candidate
from youtube import make_search, to_candidates

RESULTS = [
    {
        "videoId": "fsGjRf-N71I",
        "title": "Man I Need",
        "artists": [{"name": "Olivia Dean", "id": "UC1"}],
        "album": {"name": "The Art of Loving", "id": "MPREb"},
        "duration_seconds": 184,
        "resultType": "song",
    },
    {
        "videoId": "q36OuzoFDu8",
        "title": "Man I Need (Remix)",
        "artists": [{"name": "Hiko", "id": "UC2"}],
        "album": {"name": "Man I Need (Remix)", "id": "MPREb2"},
        "duration_seconds": 71,
        "resultType": "song",
    },
]


def test_maps_a_result_to_a_candidate():
    assert to_candidates(RESULTS)[0] == Candidate(
        video_id="fsGjRf-N71I",
        title="Man I Need",
        artist="Olivia Dean",
        album="The Art of Loving",
        duration_s=184,
    )


def test_keeps_result_order():
    assert [c.video_id for c in to_candidates(RESULTS)] == [
        "fsGjRf-N71I",
        "q36OuzoFDu8",
    ]


def test_joins_multiple_artists():
    result = dict(RESULTS[0], artists=[{"name": "Sam Fender"}, {"name": "Olivia Dean"}])
    assert to_candidates([result])[0].artist == "Sam Fender, Olivia Dean"


def test_missing_album_becomes_none():
    assert to_candidates([dict(RESULTS[0], album=None)])[0].album is None
    without = {k: v for k, v in RESULTS[0].items() if k != "album"}
    assert to_candidates([without])[0].album is None


def test_missing_artists_becomes_empty_string():
    assert to_candidates([dict(RESULTS[0], artists=None)])[0].artist == ""


def test_missing_duration_becomes_none():
    assert to_candidates([dict(RESULTS[0], duration_seconds=None)])[0].duration_s is None


def test_results_without_a_video_id_are_dropped():
    assert to_candidates([{"title": "Unplayable"}, RESULTS[0]]) == to_candidates(
        [RESULTS[0]]
    )


def test_non_dict_results_are_dropped():
    assert to_candidates(["nope", None, RESULTS[0]]) == to_candidates([RESULTS[0]])


def test_empty_results_map_to_empty():
    assert to_candidates([]) == []


class FakeClient:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.results


def test_search_returns_candidates():
    client = FakeClient(RESULTS)
    search = make_search(client=client)
    assert [c.video_id for c in search("Man I Need Olivia Dean")] == [
        "fsGjRf-N71I",
        "q36OuzoFDu8",
    ]


def test_search_asks_for_songs_only():
    client = FakeClient(RESULTS)
    make_search(client=client, limit=5)("Man I Need")
    query, kwargs = client.calls[0]
    assert query == "Man I Need"
    assert kwargs["filter"] == "songs"
    assert kwargs["limit"] == 5


def test_search_handles_a_client_returning_nothing():
    assert make_search(client=FakeClient(None))("anything") == []
