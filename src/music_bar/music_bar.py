import logging
import threading
import time
from pathlib import Path

import rumps
from AppKit import (
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
)
from pypresence import ActivityType, Presence, StatusDisplayType

from . import login_item
from .artwork import ArtworkLookup, export_current_artwork, load_menu_image
from .command import Command, applescript_string, get_playlist_names, run_script, search_library
from .dialogs import MAX_RESULTS, search_dialog, show_alert
from .mainthread import call_on_main
from .player import PlaybackClock, PlayerInfoObserver, is_music_running
from .settings import Settings
from .throttle import LatestValueSender
from .volume import VolumeHeaderMenuItem, VolumeSliderMenuItem

logger = logging.getLogger(__name__)

# Configure the package logger so messages from every music_bar module (player, command, ...) reach the log file.
package_logger = logging.getLogger("music_bar")
package_logger.setLevel(logging.DEBUG)

log_directory = Path.home() / ".music-bar"
Path.mkdir(log_directory, exist_ok=True)

handler = logging.FileHandler(log_directory / "app.log")
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
handler.setFormatter(formatter)
package_logger.addHandler(handler)

VERSION = "0.1.0"
DISCORD_APP_ID = "1326038870323892244"
APPLICATION_ICON = "assets/apple_music_white.svg"
DISCORD_ICON = "https://marketing.services.apple/api/storage/images/640a25ea26ab1a0007c2b3fd/en-us-large@2x.png"

ABOUT_TEXT = f"Author: Nick Stuer\nVersion: {VERSION}\n\n\nIcons from ReShot.com"

# Seconds between position/volume resyncs with Music while playing. Track changes and play/pause arrive instantly
# via notifications; this only corrects drift from seeking inside a track or changing volume in Music itself.
RESYNC_INTERVAL = 10
# Don't overwrite the slider from Music while the user has dragged it within this many seconds.
VOLUME_SETTLE_SECONDS = 2
VOLUME_MIN_INTERVAL = 0.1
DISCORD_ATTEMPTS = 3
ICON_SIZE = (18, 18)
SEARCH_DIALOG_ICON = "assets/music.svg"
MENU_TITLE_LENGTH = 40
MENU_BAR_TITLE_LENGTH = 30
MENU_ARTWORK_SIZE = 32
DISCORD_TEXT_MIN_LENGTH = 2  # Discord rejects shorter strings


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_dark_mode() -> bool:
    """Read the app's current effective appearance (updates live when the user switches Light/Dark)."""
    appearance = NSApplication.sharedApplication().effectiveAppearance()
    match = appearance.bestMatchFromAppearancesWithNames_([NSAppearanceNameAqua, NSAppearanceNameDarkAqua])
    return match == NSAppearanceNameDarkAqua


class MusicBar(rumps.App):
    def __init__(self, *args, **kwds):  # noqa: ANN002, ANN003, ARG002
        logger.info(f"Initializing MusicBar version {VERSION}")
        # Menu bar app: no Dock icon, but allowed to activate so dialogs get keyboard focus. Without this the policy
        # is "prohibited" (the default for an unbundled Python process, and what LSBackgroundOnly gives a bundle), so
        # windows can never become key and typing goes to whatever app was in front.
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        # Nothing in __init__ may talk to Music: any `tell application "Music"` would launch it.
        self.dark_mode = is_dark_mode()
        self.icon_items: list[tuple[rumps.MenuItem, str]] = []
        self.menu_current = rumps.MenuItem("Not Playing")
        self.menu_play = self._icon_item("Play", "assets/play.svg", self.play)
        self.menu_pause = self._icon_item("Pause", "assets/pause.svg", self.pause)
        self.menu_next = self._icon_item("Next", "assets/next.svg", self.next)
        self.menu_previous = self._icon_item("Previous", "assets/previous.svg", self.previous)
        self.menu_restart = self._icon_item("Restart", "assets/repeat.svg", self.restart)
        self.menu_search = self._icon_item("Search", "assets/search.svg", self.search_and_play)
        self.menu_playlist = self._icon_item("Playlists", "assets/menu.svg", None)
        self.menu_playlist.add(rumps.MenuItem("Open Music to load playlists"))

        # Real volume is read from Music once it's running.
        self.menu_volume_header = VolumeHeaderMenuItem("Music App Volume", value=0)
        self.menu_volume = VolumeSliderMenuItem(value=0, callback=self.set_volume, header=self.menu_volume_header)
        self.volume_sender = LatestValueSender(
            lambda value: run_script(Command.Set_Volume, round(value)),
            min_interval=VOLUME_MIN_INTERVAL,
        )
        self.last_song = None
        self.current_title = None
        self.playing = False
        self.clock = PlaybackClock()
        self.artwork = ArtworkLookup()
        self.artwork_export_lock = threading.Lock()
        # Bumped on every song change/stop and Discord update, so slow background results for an older song are dropped.
        self.track_generation = 0
        self.discord_generation = 0
        self.player_observer = PlayerInfoObserver.alloc().initWithCallback_(self.on_player_info)
        self.player_observer.start()

        self.settings = Settings.load()
        self.menu_settings = self._build_settings_menu()

        self.RPC: Presence | None = None
        if self.settings.show_discord_status:
            self.connect_discord()

        self.started = False
        self.last_discord_update_was_clear = False

        super().__init__(
            name="Music Bar",
            menu=[
                self.menu_current,
                self.menu_play,
                self.menu_pause,
                None,
                self.menu_next,
                self.menu_previous,
                self.menu_restart,
                None,
                self.menu_volume_header,
                self.menu_volume,
                None,
                self.menu_playlist,
                self.menu_search,
                None,
                self.menu_settings,
            ],
            icon=APPLICATION_ICON,
        )

    def _build_settings_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem("Settings")

        self.menu_show_discord = rumps.MenuItem("Show Discord Status", callback=self.toggle_discord_status)
        self.menu_show_discord.state = self.settings.show_discord_status
        menu.add(self.menu_show_discord)

        self.menu_show_in_bar = rumps.MenuItem("Show Song in Menu Bar", callback=self.toggle_song_in_menu_bar)
        self.menu_show_in_bar.state = self.settings.show_song_in_menu_bar
        menu.add(self.menu_show_in_bar)

        if login_item.is_supported():
            self.menu_launch_at_login = rumps.MenuItem("Launch at Login", callback=self.toggle_launch_at_login)
            self.menu_launch_at_login.state = login_item.is_enabled() or login_item.needs_approval()
        else:
            # Registering a login item needs the app bundle; from source it would register the Python interpreter.
            self.menu_launch_at_login = rumps.MenuItem("Launch at Login (built app only)")
        menu.add(self.menu_launch_at_login)
        return menu

    def toggle_discord_status(self, sender) -> None:  # noqa: ANN001
        enabled = not sender.state
        sender.state = enabled
        self.settings.show_discord_status = enabled
        self.settings.save()
        logger.info(f"Show Discord status: {enabled}")
        if enabled:
            if self.playing:
                self.update_discord_status()
        else:
            self.clear_discord_status()
            self.disconnect_discord()

    def toggle_song_in_menu_bar(self, sender) -> None:  # noqa: ANN001
        enabled = not sender.state
        sender.state = enabled
        self.settings.show_song_in_menu_bar = enabled
        self.settings.save()
        self.refresh_menu_bar_title()

    def toggle_launch_at_login(self, sender) -> None:  # noqa: ANN001
        error = login_item.set_enabled(not sender.state)
        if error:
            show_alert("Couldn't Change Launch at Login", error)
        elif login_item.needs_approval():
            show_alert(
                "Approval Needed",
                "Allow Music Bar under System Settings > General > Login Items to finish turning this on.",
            )
            login_item.open_login_items_settings()
        sender.state = login_item.is_enabled() or login_item.needs_approval()

    def refresh_menu_bar_title(self) -> None:
        """Show the current song next to the menu bar icon, if enabled and something is playing."""
        if self.settings.show_song_in_menu_bar and self.playing and self.current_title:
            self.title = shorten(self.current_title, MENU_BAR_TITLE_LENGTH)
        else:
            self.title = None

    def _icon_item(self, title: str, icon: str, callback) -> rumps.MenuItem:  # noqa: ANN001
        item = rumps.MenuItem(title, icon=icon, dimensions=ICON_SIZE, callback=callback, template=self.dark_mode)
        self.icon_items.append((item, icon))
        return item

    def refresh_icons_for_appearance(self) -> None:
        """Light mode uses the colored icons; dark mode renders them as monochrome templates."""
        dark = is_dark_mode()
        if dark == self.dark_mode:
            return
        self.dark_mode = dark
        logger.info(f"Appearance changed, dark mode: {dark}")
        for item, icon in self.icon_items:
            item.set_icon(icon, dimensions=ICON_SIZE, template=dark)

    def set_volume(self, sender) -> None:  # noqa: ANN001
        self.volume_sender.submit(sender.value)

    def play(self, _) -> None:  # noqa: ANN001
        run_script(Command.Play)

    def pause(self, _) -> None:  # noqa: ANN001
        run_script(Command.Pause)

    def next(self, _) -> None:  # noqa: ANN001
        run_script(Command.Next)

    def previous(self, _) -> None:  # noqa: ANN001
        run_script(Command.Previous)

    def restart(self, _) -> None:  # noqa: ANN001
        run_script(Command.Restart)
        # Seeking doesn't post a notification, so reset the clock and Discord timestamps ourselves.
        self.clock.sync(0, running=self.playing)
        if self.playing:
            self.update_discord_status()
            self.refresh_now_playing()

    def start_playlist(self, sender) -> None:  # noqa: ANN001
        run_script(Command.Play_Playlist_From_Name, applescript_string(sender.title))

    def search_and_play(self, _) -> None:  # noqa: ANN001
        track = search_dialog(lambda query: search_library(query, limit=MAX_RESULTS), icon_path=SEARCH_DIALOG_ICON)
        if track is not None:
            logger.info(f"Playing search result: {track.name} by {track.artist}")
            run_script(Command.Play_Song_From_ID, track.track_id)

    @rumps.clicked("About")
    def about(self, _) -> None:  # noqa: ANN001
        show_alert("Music Bar", ABOUT_TEXT, icon_path="assets/music.svg")

    def load_playlists(self) -> None:
        names = get_playlist_names()
        self.menu_playlist.clear()
        seen = set()
        for name in names:
            # Playlists are started by name, so duplicates would be ambiguous anyway (and rumps keys items by title).
            if name in seen:
                continue
            seen.add(name)
            self.menu_playlist.add(rumps.MenuItem(name, callback=self.start_playlist))

        logger.info(f"Loaded Playlists: {len(seen)}")

    @rumps.timer(1)
    def update(self, _) -> None:  # noqa: ANN001
        """Advance the elapsed-time display. Runs no AppleScript except an occasional resync."""
        self.refresh_icons_for_appearance()

        if not is_music_running():
            # Don't interact with Music app if it's not open
            if self.playing or not self.last_discord_update_was_clear:
                self.set_stopped()
            # Reload playlists and volume if Music is opened again.
            self.started = False
            return

        if not self.started:
            # First time we see Music running: load data now rather than in __init__, which would launch Music.
            self.load_playlists()
            self.menu_volume.value = run_script(Command.Get_Volume, converter=int, default=self.menu_volume.value)
            # Music may already be playing; notifications only arrive on the next change.
            self.sync_from_music()
            self.started = True
            return

        if not self.playing:
            return

        if self.clock.seconds_since_sync() >= RESYNC_INTERVAL:
            position = run_script(Command.Get_Player_Position, converter=float, default=None)
            self.clock.sync(position if position is not None else self.clock.position(), running=True)
            if self.volume_sender.seconds_since_submit() >= VOLUME_SETTLE_SECONDS:
                self.menu_volume.value = run_script(Command.Get_Volume, converter=int, default=self.menu_volume.value)

        self.refresh_now_playing()

    def on_player_info(self, info: dict) -> None:
        """Handle Music's playerInfo notification (play, pause, stop, track change)."""
        state = str(info.get("Player State", ""))
        logger.debug(f"playerInfo notification: state={state} name={info.get('Name')}")
        if state == "Playing":
            title = str(info.get("Name") or run_script(Command.Get_Current_Song_Title))
            self.set_playing(title)
        else:
            self.set_stopped()

    def sync_from_music(self) -> None:
        if run_script(Command.Get_Player_State) == "playing":
            self.set_playing(run_script(Command.Get_Current_Song_Title))
        else:
            self.set_stopped()

    def set_playing(self, title: str) -> None:
        self.playing = True
        self.current_title = title
        self.clock.sync(run_script(Command.Get_Player_Position, converter=float, default=0.0), running=True)

        if self.last_song != title:
            self.last_song = title
            logger.info(f"Current song changed: {title}")
            self.track_generation += 1
            self.refresh_menu_artwork()
            self.update_discord_status()

        if self.menu_pause.hidden:
            self.menu_pause.show()
        if not self.menu_play.hidden:
            self.menu_play.hide()

        self.refresh_now_playing()
        self.refresh_menu_bar_title()

    def set_stopped(self) -> None:
        self.playing = False
        self.clock.sync(self.clock.position(), running=False)
        self.last_song = None
        self.track_generation += 1
        self.apply_menu_artwork(self.track_generation, None)

        if self.menu_play.hidden:
            self.menu_play.show()
        if not self.menu_pause.hidden:
            self.menu_pause.hide()

        if not self.last_discord_update_was_clear:
            self.clear_discord_status()
        self.menu_current.title = "Not Playing"
        self.refresh_menu_bar_title()

    def refresh_menu_artwork(self) -> None:
        """Export the current track's cover from Music in the background and show it on the now-playing item."""
        generation = self.track_generation

        def export() -> None:
            image = None
            try:
                with self.artwork_export_lock:  # one export at a time: they all write the same file
                    path = export_current_artwork()
                    image = load_menu_image(path, MENU_ARTWORK_SIZE) if path else None
            except Exception:
                logger.exception("Failed to load artwork for the menu")
            call_on_main(lambda: self.apply_menu_artwork(generation, image))

        threading.Thread(target=export, name="ArtworkExport", daemon=True).start()

    def apply_menu_artwork(self, generation: int, image: object) -> None:
        if generation != self.track_generation:
            return  # The song changed again while this was loading.
        self.menu_current._menuitem.setImage_(image)  # noqa: SLF001 - rumps has no API for an NSImage

    def refresh_now_playing(self) -> None:
        pos = time.strftime("%M:%S", time.gmtime(self.clock.position()))
        self.menu_current.title = f"{shorten(self.current_title or '', MENU_TITLE_LENGTH)} • {pos}"

    def connect_discord(self) -> bool:
        """(Re)connect to Discord. Never raises; returns whether a connection is available."""
        try:
            rpc = Presence(DISCORD_APP_ID, pipe=0)
            rpc.connect()
        except Exception as e:  # noqa: BLE001 - pypresence raises many types when Discord isn't running
            logger.info(f"Discord not available: {e!r}")
            self.RPC = None
            return False
        self.RPC = rpc
        logger.info("Connected to Discord RPC")
        return True

    def disconnect_discord(self) -> None:
        if self.RPC is None:
            return
        try:
            self.RPC.close()
        except Exception as e:  # noqa: BLE001
            logger.info(f"Error closing Discord connection: {e!r}")
        self.RPC = None

    def clear_discord_status(self) -> None:
        logger.info("Clearing Discord status")
        self.last_discord_update_was_clear = True
        self.discord_generation += 1  # Don't let a pending artwork lookup bring the status back.
        if self.RPC is None:
            return
        try:
            self.RPC.clear()
        except Exception as e:  # noqa: BLE001
            # Discord probably quit. Drop the connection; the next status update reconnects.
            logger.info(f"Failed to clear Discord status: {e!r}")
            self.RPC = None

    def update_discord_status(self) -> None:
        if not self.settings.show_discord_status:
            return
        self.last_discord_update_was_clear = False
        self.discord_generation += 1
        generation = self.discord_generation

        artist = run_script(Command.Get_Current_Song_Artist)
        song = run_script(Command.Get_Current_Song_Title)
        album = run_script(Command.Get_Current_Song_Album)
        position = run_script(Command.Get_Player_Position, converter=float, default=0.0)
        start = run_script(Command.Get_Current_Song_Start, converter=float, default=0.0)
        finish = run_script(Command.Get_Current_Song_Finish, converter=float, default=0.0)
        duration = finish - start
        logger.info(f"Updating Discord status: {song} by {artist}, position: {position}, duration: {duration}")

        now = time.time()
        activity = {
            "details": f"{song}",
            "state": f"{artist}",
            "large_text": album if len(album) >= DISCORD_TEXT_MIN_LENGTH else None,
            # Absolute timestamps, so a later artwork update doesn't shift the progress bar.
            "start": now - int(position),
            "end": now + int(duration) - int(position),
        }

        known, artwork_url = self.artwork.cached(artist, song, album)
        self.send_discord_activity(activity, artwork_url)
        if not known:
            # Show the status right away with the Apple Music logo, then add the cover once it's found.
            self.artwork.lookup_async(
                artist,
                song,
                album,
                lambda url: call_on_main(lambda: self.apply_discord_artwork(generation, activity, url)),
            )

    def apply_discord_artwork(self, generation: int, activity: dict, artwork_url: str | None) -> None:
        if artwork_url is None or generation != self.discord_generation:
            return  # Nothing found, or the song changed / status was cleared since the lookup started.
        if not (self.playing and self.settings.show_discord_status):
            return
        self.send_discord_activity(activity, artwork_url)

    def send_discord_activity(self, activity: dict, artwork_url: str | None) -> None:
        # With a cover, the Apple Music logo moves to the small corner badge.
        images = (
            {"large_image": artwork_url, "small_image": DISCORD_ICON, "small_text": "Listening to Apple Music"}
            if artwork_url
            else {"large_image": DISCORD_ICON}
        )
        for attempt in range(1, DISCORD_ATTEMPTS + 1):
            if self.RPC is None and not self.connect_discord():
                logger.info("Discord is not running; skipping status update")
                return
            try:
                self.RPC.update(
                    activity_type=ActivityType.LISTENING,
                    status_display_type=StatusDisplayType.DETAILS,
                    **activity,
                    **images,
                )
            except Exception as e:  # noqa: BLE001
                logger.info(f"Discord update attempt {attempt} of {DISCORD_ATTEMPTS} failed: {e!r}")
                self.RPC = None  # Force a fresh connection on the next attempt.
            else:
                logger.info(f"Updated Discord status ({'with' if artwork_url else 'without'} artwork)")
                return
