import logging
import re
import time
from pathlib import Path

import darkdetect
import rumps
from pypresence import ActivityType, Presence
from pypresence.exceptions import PipeClosed

from .command import Command, run_script

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

log_directory = Path.home() / ".music-bar"
Path.mkdir(log_directory, exist_ok=True)

handler = logging.FileHandler(log_directory / "app.log")
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

VERSION = "0.0.9"
DISCORD_APP_ID = "1326038870323892244"
APPLICATION_ICON = "assets/apple_music_white.svg"
DISCORD_ICON = "https://marketing.services.apple/api/storage/images/640a25ea26ab1a0007c2b3fd/en-us-large@2x.png"

ABOUT_TEXT = f"Author: Nick Stuer\nVersion: {VERSION}\n\n\nIcons from ReShot.com"


class MusicBar(rumps.App):
    def __init__(self, *args, **kwds):  # noqa: ANN002, ANN003, ARG002
        logger.info(f"Initializing MusicBar version {VERSION}")
        self.menu_current = rumps.MenuItem("Not Playing")
        self.menu_play = rumps.MenuItem(
            "Play",
            icon="assets/play.svg",
            dimensions=(18, 18),
            callback=self.play,
            template=darkdetect.isDark(),
        )
        self.menu_pause = rumps.MenuItem(
            "Pause",
            icon="assets/pause.svg",
            dimensions=(18, 18),
            callback=self.pause,
            template=darkdetect.isDark(),
        )
        self.menu_next = rumps.MenuItem(
            "Next",
            icon="assets/next.svg",
            dimensions=(18, 18),
            callback=self.next,
            template=darkdetect.isDark(),
        )
        self.menu_previous = rumps.MenuItem(
            "Previous",
            icon="assets/previous.svg",
            dimensions=(18, 18),
            callback=self.previous,
            template=darkdetect.isDark(),
        )
        self.menu_restart = rumps.MenuItem(
            "Restart",
            icon="assets/repeat.svg",
            dimensions=(18, 18),
            callback=self.restart,
            template=darkdetect.isDark(),
        )
        self.menu_search = rumps.MenuItem(
            "Search",
            icon="assets/search.svg",
            dimensions=(18, 18),
            callback=self.search_and_play,
            template=darkdetect.isDark(),
        )
        self.menu_playlist = rumps.MenuItem(
            "Playlists",
            icon="assets/menu.svg",
            dimensions=(18, 18),
            callback=None,
            template=darkdetect.isDark(),
        )

        volume = run_script(Command.Get_Volume, converter=int)
        self.menu_volume = rumps.SliderMenuItem(dimensions=(150, 25), value=volume, callback=self.set_volume)
        self.last_song = None
        self.playing = False
        try:
            self.RPC = Presence(DISCORD_APP_ID, pipe=0)
            self.RPC.connect()
        except Exception:
            logger.exception("Failed to connect to Discord RPC - Discord might not be running")

        self.started = False
        self.last_discord_update_was_clear = False

        playlist_count = run_script(Command.Get_Playlist_Count, converter=int)
        self.menu_playlists = [rumps.MenuItem(n, callback=self.start_playlist) for n in range(1, playlist_count)]

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
                rumps.MenuItem(
                    "Music App Volume",
                ),
                self.menu_volume,
                None,
                (self.menu_playlist, self.menu_playlists),
                self.menu_search,
                None,
            ],
            icon=APPLICATION_ICON,
        )

    def set_volume(self, sender) -> None:  # noqa: ANN001
        run_script(Command.Set_Volume, sender.value)

    def play(self, _) -> None:  # noqa: ANN001
        run_script(Command.Play)

    def pause(self, _) -> None:  # noqa: ANN001
        run_script(Command.Pause)

    def next(self, _) -> None:  # noqa: ANN001
        run_script(Command.Next)

    def previous(self, _) -> None:  # noqa: ANN001
        run_script(Command.Previous)

    def restart(self, _) -> None:  # noqa: ANN001
        self.last_song = None
        run_script(Command.Restart)

    def start_playlist(self, sender) -> None:  # noqa: ANN001
        run_script(Command.Play_Playlist_From_Name, sender.title.strip())

    def search_and_play(self, _) -> None:  # noqa: ANN001
        track_id = None
        window = rumps.Window(
            "Searches your playlists for a song title and then plays it.",
            "Search Music",
            ok="Search",
            cancel="Cancel",
            dimensions=(300, 50),
        )
        window.icon = self.icon
        response = window.run()

        if not response.clicked:
            return

        playlist_count = run_script(Command.Get_Playlist_Count, converter=int)
        for playlist in range(1, playlist_count):
            result = run_script(Command.Search_Playlist_Name_For_Song, playlist, response.text)
            results = re.findall(r"\d+", result)

            if len(results) > 0:
                track_id = results[0]
                break

        if not track_id:
            rumps.alert("No Results", f"No results found for {response.text}")
        else:
            run_script(Command.Play_Song_From_ID, track_id)

    @rumps.clicked("About")
    def about(self, _) -> None:  # noqa: ANN001
        rumps.alert(
            "Music Bar",
            ABOUT_TEXT,
            icon_path="assets/music.svg",
        )

    def load_playlists(self) -> None:
        for n in range(len(self.menu_playlists)):
            self.menu_playlists[n].title = run_script(Command.Get_Playlist_Name_From_Index, n + 1)

        logger.info("Loaded Playlists:" + str(len(self.menu_playlists)))  # noqa: G003

    @rumps.timer(1)
    def update(self, _) -> None:  # noqa: ANN001, C901
        if not run_script(Command.Is_Open):
            # Don't interact with Music app if it's not open
            if not self.last_discord_update_was_clear:
                self.clear_discord_status()
            return

        if not self.started:
            # Load Playlists after the app is started because it might take some time and block the icon from showing
            self.load_playlists()
            self.started = True

        self.playing = run_script(Command.Get_Player_State) == "playing"

        if self.playing:
            volume = run_script(Command.Get_Volume, converter=int)
            self.menu_volume.value = volume

            current_song = run_script(Command.Get_Current_Song_Title)
            if self.last_song != current_song:
                self.last_song = current_song
                logger.info(f"Current song changed: {current_song}")
                self.update_discord_status()

            pos = run_script(Command.Get_Player_Position)
            pos = time.strftime("%M:%S", time.gmtime(float(pos)))
            title = run_script(Command.Get_Current_Song_Title)

            title_short = title if len(title) <= 40 else title[: 40 - 1] + "…"  # noqa: PLR2004
            self.menu_current.title = f"{title_short} • {pos}"

            if self.menu_pause.hidden:
                self.menu_pause.show()

            if not self.menu_play.hidden:
                self.menu_play.hide()

        else:
            if self.menu_play.hidden:
                self.menu_play.show()

            if not self.menu_pause.hidden:
                self.menu_pause.hide()

            if not self.last_discord_update_was_clear:
                self.clear_discord_status()
            self.last_song = None
            self.menu_current.title = "Not Playing"

    def clear_discord_status(self) -> None:
        logger.info("Clearing Discord status")
        self.last_discord_update_was_clear = True
        self.RPC.clear()

    def update_discord_status(self) -> None:
        self.last_discord_update_was_clear = False

        attempts = 0
        while attempts < 3:  # noqa: PLR2004
            attempts += 1
            logger.info(f"Attempting to update Discord status, attempt {attempts} of 3")
            try:
                artist = run_script(Command.Get_Current_Song_Artist)
                song = run_script(Command.Get_Current_Song_Title)
                position = run_script(Command.Get_Player_Position, converter=float)

                finish = run_script(Command.Get_Current_Song_Finish, converter=float) - position
                start = run_script(Command.Get_Current_Song_Start, converter=float) - position
                duration = finish - start

                logger.info(f"Updating Discord status: {song} by {artist}, position: {position}, duration: {duration}")

                self.RPC.update(
                    activity_type=ActivityType.LISTENING,
                    details=f"{song}",
                    state=f"{artist}",
                    large_image=DISCORD_ICON,
                    start=time.time() - int(position),
                    end=time.time() + int(duration) - int(position),
                    small_text="Listening to Apple Music",
                )
                logger.info("Updated Discord status!")
                return  # noqa: TRY300
            except PipeClosed:
                logger.info("Broken pipe error, reconnecting to Discord RPC")
                self.RPC.connect()
            except ConnectionRefusedError:
                logger.info("Connection refused error - discord is not running")
            except AssertionError:
                logger.info("Discord wasn't open when Music Bar launched, connecting to Discord RPC")
                self.RPC = Presence(DISCORD_APP_ID, pipe=0)
                self.RPC.connect()
            except Exception as e:
                logger.exception(f"Failed to update Discord status {e}")  # noqa: TRY401
