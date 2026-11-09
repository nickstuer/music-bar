import threading
from unittest.mock import patch

import pytest

from music_bar import artwork
from music_bar.artwork import ArtworkLookup, export_current_artwork, pick_artwork_url

THUMB = "https://is1-ssl.mzstatic.com/image/thumb/Music/x/{}.jpg/100x100bb.jpg"


def result(artist, track, album, name="a"):
    return {"artistName": artist, "trackName": track, "collectionName": album, "artworkUrl100": THUMB.format(name)}


def test_upscales_thumbnail():
    url = pick_artwork_url([result("Artist", "Song", "Album")], "Artist", "Song", "Album")
    assert url == THUMB.format("a").replace("100x100bb", "512x512bb")


def test_prefers_matching_album_over_remix_or_reissue():
    results = [
        result("Empire Of The Sun", "Walking On A Dream (Remix)", "Walking On A Dream (Remix) - Single", "remix"),
        result("Empire Of The Sun", "Walking on a Dream", "Walking on a Dream (10th Anniversary Edition)", "reissue"),
        result("Empire Of The Sun", "Walking on a Dream", "Walking on a Dream", "original"),
    ]
    url = pick_artwork_url(results, "Empire Of The Sun", "Walking On a Dream", "Walking On a Dream")
    assert "original" in url


def test_album_prefix_beats_other_albums():
    results = [
        result("Artist", "Song", "Greatest Hits", "hits"),
        result("Artist", "Song", "Album (Deluxe Edition)", "deluxe"),
    ]
    assert "deluxe" in pick_artwork_url(results, "Artist", "Song", "Album")


def test_never_uses_another_artists_cover():
    assert pick_artwork_url([result("Someone Else", "Song", "Album")], "Artist", "Song", "Album") is None


def test_featured_artist_still_matches():
    assert pick_artwork_url([result("Artist & Friend", "Song", "Album")], "Artist", "Song", "Album") is not None


def test_no_results():
    assert pick_artwork_url([], "Artist", "Song", "Album") is None
    assert pick_artwork_url([{"artistName": "Artist"}], "Artist", "Song", "Album") is None  # no artwork url


def test_lookup_caches_hits_and_misses():
    calls = []

    def fetch(artist, title):
        calls.append((artist, title))
        return [result("Artist", "Song", "Album")] if title == "Song" else []

    lookup = ArtworkLookup(fetch=fetch)
    assert lookup.cached("Artist", "Song", "Album") == (False, None)
    url = lookup.lookup("Artist", "Song", "Album")
    assert lookup.lookup("artist", "song", "album") == url  # normalized key, no second fetch
    assert lookup.lookup("Artist", "Unknown", "Album") is None
    assert lookup.cached("Artist", "Unknown", "Album") == (True, None)
    assert calls == [("Artist", "Song"), ("Artist", "Unknown")]


def test_network_errors_are_not_cached():
    attempts = []

    def fetch(*_: object):
        attempts.append(1)
        raise TimeoutError

    lookup = ArtworkLookup(fetch=fetch)
    assert lookup.lookup("Artist", "Song", "Album") is None
    assert lookup.cached("Artist", "Song", "Album") == (False, None)
    lookup.lookup("Artist", "Song", "Album")
    assert len(attempts) == 2


def test_lookup_async_reports_unexpected_errors_as_none():
    def fetch(*_: object):
        raise KeyError

    done = threading.Event()
    received = []
    ArtworkLookup(fetch=fetch).lookup_async("A", "S", "Al", lambda url: (received.append(url), done.set()))
    assert done.wait(2)
    assert received == [None]


def test_default_fetch_is_blocked_in_tests():
    # Guard from conftest: a real network request would fail loudly instead of hitting Apple's API.
    with pytest.raises(AssertionError):
        artwork._fetch_results("Artist", "Song")  # noqa: SLF001


@pytest.mark.parametrize(("output", "expected_found"), [("ok", True), ("none", False), ("", False)])
def test_export_current_artwork(tmp_path, output, expected_found):
    path = tmp_path / "art" / "cover"
    with patch.object(artwork, "run_raw_script", return_value=output) as run:
        assert (export_current_artwork(path) == path) is expected_found
    script = run.call_args[0][0]
    assert f'POSIX file "{path}"' in script
    assert path.parent.is_dir()
