import logging

import pytest

import music_bar.music_bar  # noqa: F401 - configures the package logger on import

# Keep test runs out of the user's real ~/.music-bar/app.log.
for handler in list(logging.getLogger("music_bar").handlers):
    if isinstance(handler, logging.FileHandler):
        logging.getLogger("music_bar").removeHandler(handler)
        handler.close()


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Keep tests from reading or writing the user's real ~/.music-bar/settings.json."""
    from music_bar import settings  # noqa: PLC0415

    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    return path


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch):
    """Fail loudly if a test would run real AppleScript against Music or make a real network request.

    Tests that need these patch them explicitly (a per-test patch overrides this).
    """
    from music_bar import artwork, command  # noqa: PLC0415

    def forbidden(*_: object, **__: object) -> None:
        msg = "tests must not run real osascript or network requests"
        raise AssertionError(msg)

    monkeypatch.setattr(command, "osascript", forbidden)
    monkeypatch.setattr(artwork.urllib.request, "urlopen", forbidden)
