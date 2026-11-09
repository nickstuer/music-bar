from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_bar import music_bar as mb
from music_bar.artwork import ArtworkLookup
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
        instance.artwork = ArtworkLookup(fetch=lambda *_: [])
        monkeypatch.setattr(instance, "refresh_menu_artwork", MagicMock())
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
    assert "bundle_identifier='com.nickstuer.musicbar'" in spec


# --- Settings menu -----------------------------------------------------------------------------------------------


def test_settings_menu_items(app):
    assert list(app.menu_settings.keys()) == [
        "Show Discord Status",
        "Show Song in Menu Bar",
        "Launch at Login (built app only)",
    ]
    assert app.menu_show_discord.state
    assert not app.menu_show_in_bar.state


def test_disable_discord_clears_and_disconnects(app, isolated_settings):
    rpc = MagicMock()
    app.RPC = rpc
    app.toggle_discord_status(app.menu_show_discord)
    assert not app.menu_show_discord.state
    rpc.clear.assert_called_once()
    rpc.close.assert_called_once()
    assert app.RPC is None
    assert '"show_discord_status": false' in isolated_settings.read_text()


def test_disabled_discord_never_updates_or_connects(app):
    app.settings.show_discord_status = False
    app.RPC = None
    app.presence.reset_mock()
    app.update_discord_status()
    app.presence.assert_not_called()
    app.run_script.assert_not_called()


def test_reenable_discord_updates_when_playing(app):
    app.settings.show_discord_status = False
    app.menu_show_discord.state = False
    app.playing = True
    with patch.object(app, "update_discord_status") as update:
        app.toggle_discord_status(app.menu_show_discord)
    update.assert_called_once()


def test_disabled_discord_skips_connect_on_startup(monkeypatch):
    monkeypatch.chdir(SRC)
    mb.Settings(show_discord_status=False).save()
    with patch.object(mb, "Presence") as presence, patch.object(mb, "run_script"):
        instance = mb.MusicBar()
        instance.player_observer.stop()
    presence.assert_not_called()


def test_song_in_menu_bar(app, isolated_settings):
    app.playing, app.current_title = True, "A Very Long Song Title That Keeps Going On"
    app.refresh_menu_bar_title()
    assert app.title is None  # off by default

    app.toggle_song_in_menu_bar(app.menu_show_in_bar)
    assert app.title == mb.shorten(app.current_title, mb.MENU_BAR_TITLE_LENGTH)
    assert len(app.title) == mb.MENU_BAR_TITLE_LENGTH
    assert '"show_song_in_menu_bar": true' in isolated_settings.read_text()

    app.set_stopped()
    assert app.title is None


def test_launch_at_login_menu_when_built(monkeypatch):
    monkeypatch.chdir(SRC)
    with (
        patch.object(mb, "Presence"),
        patch.object(mb, "run_script"),
        patch.object(mb.login_item, "is_supported", return_value=True),
        patch.object(mb.login_item, "is_enabled", return_value=False),
        patch.object(mb.login_item, "needs_approval", return_value=False),
    ):
        instance = mb.MusicBar()
        instance.player_observer.stop()
    assert instance.menu_launch_at_login.title == "Launch at Login"
    assert instance.menu_launch_at_login.callback == instance.toggle_launch_at_login


def test_toggle_launch_at_login_needing_approval(app):
    sender = MagicMock(state=False)
    with (
        patch.object(mb.login_item, "set_enabled", return_value=None) as set_enabled,
        patch.object(mb.login_item, "needs_approval", return_value=True),
        patch.object(mb.login_item, "is_enabled", return_value=False),
        patch.object(mb.login_item, "open_login_items_settings") as open_settings,
        patch.object(mb, "show_alert") as alert,
    ):
        app.toggle_launch_at_login(sender)
    set_enabled.assert_called_once_with(True)  # noqa: FBT003
    alert.assert_called_once()
    open_settings.assert_called_once()
    assert sender.state


def test_toggle_launch_at_login_error(app):
    sender = MagicMock(state=False)
    with (
        patch.object(mb.login_item, "set_enabled", return_value="nope"),
        patch.object(mb.login_item, "needs_approval", return_value=False),
        patch.object(mb.login_item, "is_enabled", return_value=False),
        patch.object(mb, "show_alert") as alert,
    ):
        app.toggle_launch_at_login(sender)
    alert.assert_called_once_with("Couldn't Change Launch at Login", "nope")
    assert not sender.state


# --- Artwork -----------------------------------------------------------------------------------------------------

COVER = "https://example.com/cover/512x512bb.jpg"


def song_info(command, *_: object, **kw: object):
    return {
        Command.Get_Current_Song_Artist: "Artist",
        Command.Get_Current_Song_Title: "Song",
        Command.Get_Current_Song_Album: "Album",
    }.get(command, kw.get("default", ""))


def test_discord_uses_cached_artwork_immediately(app):
    app.run_script.side_effect = song_info
    app.artwork = MagicMock()
    app.artwork.cached.return_value = (True, COVER)
    app.RPC = MagicMock()
    app.update_discord_status()
    kwargs = app.RPC.update.call_args.kwargs
    assert kwargs["large_image"] == COVER
    assert kwargs["small_image"] == mb.DISCORD_ICON
    assert kwargs["large_text"] == "Album"
    app.artwork.lookup_async.assert_not_called()


def test_discord_shows_logo_then_adds_artwork(app):
    app.run_script.side_effect = song_info
    app.artwork = MagicMock()
    app.artwork.cached.return_value = (False, None)
    app.RPC = MagicMock()
    app.playing = True
    with patch.object(mb, "call_on_main", side_effect=lambda fn: fn()):
        app.update_discord_status()
        first = app.RPC.update.call_args.kwargs
        assert first["large_image"] == mb.DISCORD_ICON
        assert "small_image" not in first

        callback = app.artwork.lookup_async.call_args[0][3]
        callback(COVER)  # lookup finished
    second = app.RPC.update.call_args.kwargs
    assert second["large_image"] == COVER
    assert (second["start"], second["end"]) == (first["start"], first["end"])  # progress bar not shifted


def test_late_artwork_ignored_after_song_change_or_clear(app):
    app.RPC = MagicMock()
    app.playing = True
    activity = {"details": "Song", "state": "Artist", "start": 0, "end": 1}

    stale = app.discord_generation
    app.discord_generation += 1  # a newer update happened
    app.apply_discord_artwork(stale, activity, COVER)
    app.RPC.update.assert_not_called()

    current = app.discord_generation
    app.clear_discord_status()
    app.apply_discord_artwork(current, activity, COVER)
    app.RPC.update.assert_not_called()


def test_short_album_omitted_for_discord(app):
    app.run_script.side_effect = lambda c, *_, **kw: "A" if c == Command.Get_Current_Song_Album else song_info(c, **kw)
    app.artwork = MagicMock()
    app.artwork.cached.return_value = (True, None)
    app.RPC = MagicMock()
    app.update_discord_status()
    assert app.RPC.update.call_args.kwargs["large_text"] is None


def test_song_change_refreshes_menu_artwork(app):
    app.run_script.side_effect = song_info
    app.set_playing("Song")
    app.refresh_menu_artwork.assert_called_once()
    app.set_playing("Song")  # same song (e.g. resume) - no reload
    app.refresh_menu_artwork.assert_called_once()


def test_menu_artwork_applied_only_for_current_song(app):
    image = MagicMock()
    app.menu_current._menuitem = MagicMock()  # noqa: SLF001 - PyObjC methods can't be patched individually
    set_image = app.menu_current._menuitem.setImage_  # noqa: SLF001
    app.apply_menu_artwork(app.track_generation - 1, image)
    set_image.assert_not_called()
    app.apply_menu_artwork(app.track_generation, image)
    set_image.assert_called_once_with(image)


def test_stopping_clears_menu_artwork(app):
    app.menu_current._menuitem = MagicMock()  # noqa: SLF001
    app.set_stopped()
    app.menu_current._menuitem.setImage_.assert_called_once_with(None)  # noqa: SLF001
