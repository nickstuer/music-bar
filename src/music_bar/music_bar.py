import logging
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

from .command import Command, applescript_string, get_playlist_names, run_script, search_library
from .dialogs import MAX_RESULTS, search_dialog, show_alert
from .player import PlaybackClock, PlayerInfoObserver, is_music_running
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

VERSION = "0.0.12"
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
        self.player_observer = PlayerInfoObserver.alloc().initWithCallback_(self.on_player_info)
        self.player_observer.start()

        self.RPC: Presence | None = None
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
            ],
            icon=APPLICATION_ICON,
        )

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
            self.update_discord_status()

        if self.menu_pause.hidden:
            self.menu_pause.show()
        if not self.menu_play.hidden:
            self.menu_play.hide()

        self.refresh_now_playing()

    def set_stopped(self) -> None:
        self.playing = False
        self.clock.sync(self.clock.position(), running=False)
        self.last_song = None

        if self.menu_play.hidden:
            self.menu_play.show()
        if not self.menu_pause.hidden:
            self.menu_pause.hide()

        if not self.last_discord_update_was_clear:
            self.clear_discord_status()
        self.menu_current.title = "Not Playing"

    def refresh_now_playing(self) -> None:
        pos = time.strftime("%M:%S", time.gmtime(self.clock.position()))
        title = self.current_title or ""
        title_short = title if len(title) <= 40 else title[: 40 - 1] + "…"  # noqa: PLR2004
        self.menu_current.title = f"{title_short} • {pos}"

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

    def clear_discord_status(self) -> None:
        logger.info("Clearing Discord status")
        self.last_discord_update_was_clear = True
        if self.RPC is None:
            return
        try:
            self.RPC.clear()
        except Exception as e:  # noqa: BLE001
            # Discord probably quit. Drop the connection; the next status update reconnects.
            logger.info(f"Failed to clear Discord status: {e!r}")
            self.RPC = None

    def update_discord_status(self) -> None:
        self.last_discord_update_was_clear = False

        artist = run_script(Command.Get_Current_Song_Artist)
        song = run_script(Command.Get_Current_Song_Title)
        position = run_script(Command.Get_Player_Position, converter=float, default=0.0)
        start = run_script(Command.Get_Current_Song_Start, converter=float, default=0.0)
        finish = run_script(Command.Get_Current_Song_Finish, converter=float, default=0.0)
        duration = finish - start
        logger.info(f"Updating Discord status: {song} by {artist}, position: {position}, duration: {duration}")

        for attempt in range(1, DISCORD_ATTEMPTS + 1):
            if self.RPC is None and not self.connect_discord():
                logger.info("Discord is not running; skipping status update")
                return
            try:
                self.RPC.update(
                    activity_type=ActivityType.LISTENING,
                    status_display_type=StatusDisplayType.DETAILS,
                    details=f"{song}",
                    state=f"{artist}",
                    large_image=DISCORD_ICON,
                    start=time.time() - int(position),
                    end=time.time() + int(duration) - int(position),
                    small_text="Listening to Apple Music",
                )
            except Exception as e:  # noqa: BLE001
                logger.info(f"Discord update attempt {attempt} of {DISCORD_ATTEMPTS} failed: {e!r}")
                self.RPC = None  # Force a fresh connection on the next attempt.
            else:
                logger.info("Updated Discord status!")
                return
