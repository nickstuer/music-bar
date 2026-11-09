"""Album artwork: exported from Music for the menu, and looked up online for Discord.

Discord can only show images from a public URL, so local artwork can't be uploaded to it. Instead the track is looked
up in Apple's public iTunes Search API, which returns a CDN URL for the album cover.
"""

import json
import logging
import re
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from AppKit import NSImage

from .command import applescript_string, run_raw_script

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_TIMEOUT = 5
DISCORD_ARTWORK_SIZE = 512
CACHE_LIMIT = 500
ARTWORK_PATH = Path.home() / ".music-bar" / "current-artwork"

EXPORT_ARTWORK_SCRIPT = """
tell application "Music"
    if (count of artworks of current track) is 0 then return "none"
    set artData to raw data of artwork 1 of current track
end tell
set f to open for access (POSIX file {path}) with write permission
try
    set eof f to 0
    write artData to f
    close access f
on error errMsg
    close access f
    error errMsg
end try
return "ok"
"""


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _score(result: dict, artist: str, title: str, album: str) -> int:
    """Score an iTunes search result against the playing track; 0 means it's not a credible match."""
    want_artist, got_artist = _normalize(artist), _normalize(result.get("artistName", ""))
    if not want_artist or not got_artist:
        return 0
    if want_artist == got_artist:
        score = 4
    elif want_artist in got_artist or got_artist in want_artist:
        score = 2  # e.g. "Artist" vs "Artist feat. Someone"
    else:
        return 0  # Never use a different artist's cover.

    if _normalize(result.get("trackName", "")) == _normalize(title):
        score += 2
    want_album, got_album = _normalize(album), _normalize(result.get("collectionName", ""))
    if want_album and got_album == want_album:
        score += 3
    elif want_album and got_album.startswith(want_album):
        score += 1  # e.g. "Album" vs "Album (Deluxe Edition)"
    return score


def pick_artwork_url(results: list[dict], artist: str, title: str, album: str) -> str | None:
    """Choose the best-matching result's artwork, upscaled from the 100px thumbnail to DISCORD_ARTWORK_SIZE."""
    best_url, best_score = None, 0
    for result in results:
        url = result.get("artworkUrl100")
        score = _score(result, artist, title, album)
        if url and score > best_score:
            best_url, best_score = url, score
    if best_url is None:
        return None
    size = DISCORD_ARTWORK_SIZE
    return re.sub(r"/\d+x\d+bb\.(jpg|png|webp)$", rf"/{size}x{size}bb.\1", best_url)


def _fetch_results(artist: str, title: str) -> list[dict]:
    query = urllib.parse.urlencode({"term": f"{artist} {title}", "entity": "song", "media": "music", "limit": 10})
    request = urllib.request.Request(f"{ITUNES_SEARCH_URL}?{query}", headers={"User-Agent": "MusicBar"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=LOOKUP_TIMEOUT) as response:  # noqa: S310 - fixed https URL
        return json.load(response).get("results", [])


class ArtworkLookup:
    """Caches artwork URLs per track and fetches missing ones on a background thread."""

    def __init__(self, fetch: Callable[[str, str], list[dict]] = _fetch_results) -> None:
        self._fetch = fetch
        self._cache: dict[tuple[str, str, str], str | None] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(artist: str, title: str, album: str) -> tuple[str, str, str]:
        return _normalize(artist), _normalize(title), _normalize(album)

    def cached(self, artist: str, title: str, album: str) -> tuple[bool, str | None]:
        """Return (known, url). ``known`` is False when the track hasn't been looked up yet."""
        key = self._key(artist, title, album)
        with self._lock:
            return (key in self._cache, self._cache.get(key))

    def lookup(self, artist: str, title: str, album: str) -> str | None:
        """Blocking lookup (call from a background thread). Network failures aren't cached, so they're retried."""
        known, url = self.cached(artist, title, album)
        if known:
            return url
        try:
            results = self._fetch(artist, title)
        except (OSError, ValueError) as e:
            logger.info(f"Artwork lookup failed for {artist} - {title}: {e!r}")
            return None
        url = pick_artwork_url(results, artist, title, album)
        logger.info(f"Artwork for {artist} - {title}: {url or 'not found'}")
        with self._lock:
            if len(self._cache) >= CACHE_LIMIT:
                self._cache.clear()
            self._cache[self._key(artist, title, album)] = url
        return url

    def lookup_async(self, artist: str, title: str, album: str, callback: Callable[[str | None], None]) -> None:
        """Look up on a background thread and pass the URL (or None) to ``callback`` on that thread."""

        def run() -> None:
            try:
                url = self.lookup(artist, title, album)
            except Exception:
                logger.exception(f"Unexpected error looking up artwork for {artist} - {title}")
                url = None
            callback(url)

        threading.Thread(target=run, name="ArtworkLookup", daemon=True).start()


def export_current_artwork(path: Path = ARTWORK_PATH) -> Path | None:
    """Write the current track's embedded artwork to ``path``. Returns the path, or None if there's no artwork."""
    path.parent.mkdir(parents=True, exist_ok=True)
    result = run_raw_script(EXPORT_ARTWORK_SCRIPT.format(path=applescript_string(str(path))))
    if result != "ok":
        if result != "none":
            logger.info(f"Could not export artwork: {result!r}")
        return None
    return path


def load_menu_image(path: Path, size: float) -> NSImage | None:
    image = NSImage.alloc().initWithContentsOfFile_(str(path))
    if image is None:
        return None
    image.setSize_((size, size))
    return image
