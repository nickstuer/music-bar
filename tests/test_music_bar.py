from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_bar import music_bar as mb
from music_bar.command import Command, Track

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.chdir(SRC)  # icons are loaded relative to src/
    with (
        patch.object(mb, "Presence") as presence,
        patch.object(mb, "run_script") as run_script,
        patch.object(mb, "is_music_running", return_value=True),
    ):
        presence.return_value = MagicMock()
        instance = mb.MusicBar()
        instance.player_observer.stop()
        instance.run_script = run_script  # expose for assertions
        instance.presence = presence
        yield instance


def test_init_does_not_talk_to_music(monkeypatch):
    monkeypatch.chdir(SRC)
    with patch.object(mb, "Presence"), patch.object(mb, "run_script") as run_script:
        instance = mb.MusicBar()
        instance.player_observer.stop()
    run_script.assert_not_called()


def test_load_playlists_includes_last(app):
    with patch.object(mb, "get_playlist_names", return_value=["Library", "Chill", "Workout", "Chill"]):
        app.load_playlists()
    assert list(app.menu_playlist.keys()) == ["Library", "Chill", "Workout"]


def test_start_playlist_quotes_name(app):
    app.start_playlist(MagicMock(title='My "Best" Mix'))
    app.run_script.assert_called_once_with(Command.Play_Playlist_From_Name, '"My \\"Best\\" Mix"')


def test_first_tick_loads_once_music_runs(app):
    app.run_script.side_effect = lambda command, *_, **kw: {
        Command.Get_Volume: 55,
        Command.Get_Player_State: "paused",
    }.get(command, kw.get("default", ""))
    with patch.object(mb, "get_playlist_names", return_value=["Library"]):
        app.update(None)
    assert app.started
    assert app.menu_volume.value == 55
    assert not app.playing


def test_music_quitting_resets_started(app):
    app.started = True
    with patch.object(mb, "is_music_running", return_value=False):
        app.update(None)
    assert not app.started


def test_clear_discord_survives_errors(app):
    app.RPC = MagicMock()
    app.RPC.clear.side_effect = BrokenPipeError
    app.last_discord_update_was_clear = False
    app.clear_discord_status()  # must not raise
    assert app.RPC is None
    assert app.last_discord_update_was_clear


def test_clear_discord_without_connection(app):
    app.RPC = None
    app.clear_discord_status()  # must not raise


def test_update_discord_skips_when_discord_unavailable(app):
    app.RPC = None
    app.run_script.side_effect = lambda *_, **kw: kw.get("default", "x")
    app.presence.return_value.connect.side_effect = ConnectionRefusedError
    app.update_discord_status()  # must not raise
    assert app.RPC is None


def test_update_discord_reconnects_after_failure(app):
    app.run_script.side_effect = lambda *_, **kw: kw.get("default", "x")
    broken = MagicMock()
    broken.update.side_effect = BrokenPipeError
    app.RPC = broken
    fresh = MagicMock()
    app.presence.return_value = fresh
    app.update_discord_status()
    fresh.update.assert_called_once()


def test_icons_follow_appearance_changes(app):
    item, icon = app.icon_items[0]
    with patch.object(mb, "is_dark_mode", return_value=not app.dark_mode), patch.object(item, "set_icon") as set_icon:
        app.refresh_icons_for_appearance()
    set_icon.assert_called_once_with(icon, dimensions=mb.ICON_SIZE, template=app.dark_mode)


def test_search_plays_chosen_track(app):
    track = Track(42, "Song", "Artist")
    with patch.object(mb, "search_dialog", return_value=track):
        app.search_and_play(None)
    app.run_script.assert_called_once_with(Command.Play_Song_From_ID, 42)


def test_search_cancelled_plays_nothing(app):
    with patch.object(mb, "search_dialog", return_value=None):
        app.search_and_play(None)
    app.run_script.assert_not_called()


def test_init_sets_accessory_activation_policy(monkeypatch):
    monkeypatch.chdir(SRC)
    ns_application = MagicMock()
    with (
        patch.object(mb, "Presence"),
        patch.object(mb, "run_script"),
        patch.object(mb, "NSApplication", ns_application),
        patch.object(mb, "is_dark_mode", return_value=False),
    ):
        instance = mb.MusicBar()
        instance.player_observer.stop()
    ns_application.sharedApplication().setActivationPolicy_.assert_called_once_with(
        mb.NSApplicationActivationPolicyAccessory,
    )


def test_bundle_is_not_background_only():
    spec = (SRC.parent / "musicbar.spec").read_text()
    assert "'LSUIElement': True" in spec
    assert "LSBackgroundOnly" not in spec
