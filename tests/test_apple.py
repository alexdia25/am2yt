from pathlib import Path

import pytest

from apple import AppleParseError, parse_playlist

FIXTURE = Path(__file__).parent / "fixtures" / "todays-hits.html"


@pytest.fixture(scope="module")
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_playlist_name(html):
    assert parse_playlist(html).name == "Today’s Hits"


def test_parses_all_embedded_tracks(html):
    assert len(parse_playlist(html).tracks) == 50


def test_parses_first_track_fields(html):
    track = parse_playlist(html).tracks[0]
    assert track.apple_id == "1817609509"
    assert track.title == "Man I Need"
    assert track.artist == "Olivia Dean"
    assert track.album == "The Art of Loving"
    assert track.duration_ms == 184000


def test_reads_reported_total_from_footer(html):
    assert parse_playlist(html).reported_total == 50


def test_every_track_has_an_id_and_title(html):
    for track in parse_playlist(html).tracks:
        assert track.apple_id
        assert track.title


def test_rejects_html_without_server_data():
    with pytest.raises(AppleParseError, match="serialized-server-data"):
        parse_playlist("<html><body>nope</body></html>")


def test_rejects_server_data_with_unexpected_shape():
    html = '<script id="serialized-server-data">{"data": []}</script>'
    with pytest.raises(AppleParseError, match="page structure"):
        parse_playlist(html)


def test_rejects_invalid_json():
    html = '<script id="serialized-server-data">{not json</script>'
    with pytest.raises(AppleParseError, match="JSON"):
        parse_playlist(html)


def test_fetch_decodes_utf8_when_the_server_omits_the_charset(monkeypatch, html):
    """Apple sends "Content-Type: text/html" with no charset, so requests guesses
    ISO-8859-1 and mangles the curly apostrophe in a name like "Today's Hits".
    fetch_playlist must override that guess."""
    import apple

    class FakeResponse:
        def __init__(self):
            self.content = html.encode("utf-8")
            self.encoding = "ISO-8859-1"
            self.apparent_encoding = "utf-8"

        @property
        def text(self):
            return self.content.decode(self.encoding, errors="replace")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(apple.requests, "get", lambda *a, **k: FakeResponse())
    assert apple.fetch_playlist("https://music.apple.com/us/playlist/x/pl.1").name == (
        "Today’s Hits"
    )
