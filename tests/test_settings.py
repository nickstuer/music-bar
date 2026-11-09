import json

from music_bar.settings import Settings


def test_defaults_when_missing(isolated_settings):
    assert not isolated_settings.exists()
    assert Settings.load() == Settings(show_discord_status=True, show_song_in_menu_bar=False)


def test_round_trip(isolated_settings):
    Settings(show_discord_status=False, show_song_in_menu_bar=True).save()
    assert json.loads(isolated_settings.read_text()) == {"show_discord_status": False, "show_song_in_menu_bar": True}
    assert Settings.load() == Settings(show_discord_status=False, show_song_in_menu_bar=True)
    assert not isolated_settings.with_suffix(".tmp").exists()


def test_corrupt_file_uses_defaults(isolated_settings):
    isolated_settings.write_text("{not json")
    assert Settings.load() == Settings()


def test_non_object_uses_defaults(isolated_settings):
    isolated_settings.write_text("[1, 2]")
    assert Settings.load() == Settings()


def test_invalid_and_unknown_keys(isolated_settings):
    isolated_settings.write_text(json.dumps({"show_discord_status": "yes", "show_song_in_menu_bar": True, "x": 1}))
    assert Settings.load() == Settings(show_discord_status=True, show_song_in_menu_bar=True)


def test_save_creates_directory(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    Settings().save(path)
    assert path.exists()
