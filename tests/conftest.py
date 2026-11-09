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
