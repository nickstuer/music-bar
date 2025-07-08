import re
import time

import darkdetect
import rumps
from pypresence import ActivityType, Presence

from command import Command, run_script, run_script_float, run_script_int

VERSION = "0.0.3"
DISCORD_APP_ID = "1326038870323892244"
APPLICATION_ICON = "assets/apple_music.svg"
DISCORD_ICON = "https://marketing.services.apple/api/storage/images/640a25ea26ab1a0007c2b3fd/en-us-large@2x.png"

ABOUT_TEXT = f"Author: Nick Stuer\nVersion: {VERSION}\n\n\nIcons from ReShot.com"


class MusicBar(rumps.App):
    def __init__(self, *args, **kwds):
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
            callback=self.searchAndPlay,
            template=darkdetect.isDark(),
        )
        self.menu_playlist = rumps.MenuItem(
            "Playlists",
            icon="assets/menu.svg",
            dimensions=(18, 18),
            callback=None,
            template=darkdetect.isDark(),
        )

        volume = run_script_int(Command.Get_Volume)
        self.menu_volume = rumps.SliderMenuItem(
            dimensions=(150, 25), value=volume, callback=self.set_volume
        )
        self.last_song = None
        self.playing = False
        self.RPC = Presence(DISCORD_APP_ID, pipe=0)
        self.RPC.connect()
        self.started = False
        self.last_discord_update_was_clear = False

        playlist_count = run_script_int(Command.Get_Playlist_Count)
        self.menu_playlists = [
            rumps.MenuItem(n, callback=self.start_playlist)
            for n in range(1, playlist_count)
        ]

        super(MusicBar, self).__init__(
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

    def set_volume(self, sender):
        run_script(Command.Set_Volume, sender.value)

    def play(self, _):
        run_script(Command.Play)

    def pause(self, _):
        run_script(Command.Pause)

    def next(self, _):
        run_script(Command.Next)

    def previous(self, _):
        run_script(Command.Previous)

    def restart(self, _):
        self.last_song = None
        run_script(Command.Restart)

    def start_playlist(self, sender):
        run_script(Command.Play_Playlist_From_Name, sender.title.strip())

    def searchAndPlay(self, _):
        trackID = None
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

        playlist_count = run_script_int(Command.Get_Playlist_Count)
        for playlist in range(1, playlist_count):
            result = run_script(
                Command.Search_Playlist_Name_For_Song, playlist, response.text
            )
            results = re.findall(r"\d+", result)

            if len(results) > 0:
                trackID = results[0]
                break

        if not trackID:
            rumps.alert("No Results", f"No results found for {response.text}")
        else:
            run_script(Command.Play_Song_From_ID, trackID)

    @rumps.clicked("About")
    def about(self, _):
        rumps.alert(
            "Music Bar",
            ABOUT_TEXT,
            icon_path="assets/music.svg",
        )

    def load_playlists(self):
        for n in range(0, len(self.menu_playlists)):
            self.menu_playlists[n].title = run_script(
                Command.Get_Playlist_Name_From_Index, n + 1
            )

    @rumps.timer(1)
    def update(self, _):
        if not run_script(Command.Is_Open):
            # Don't interact with Music app if it's not open
            if not self.last_discord_update_was_clear:
                self.clear_discord_status()
            return

        if not self.started:
            # Load Playlists after the app is started because it might take some time and block the icon from showing immediately
            self.load_playlists()
            self.started = True

        self.playing = (
            True if run_script(Command.Get_Player_State) == "playing" else False
        )

        if self.playing:
            volume = run_script_int(Command.Get_Volume)
            self.menu_volume.value = volume

            current_song = run_script(Command.Get_Current_Song_Title)
            if self.last_song != current_song:
                self.last_song = current_song
                self.update_discord_status()

            pos = run_script(Command.Get_Player_Position)
            pos = time.strftime("%M:%S", time.gmtime(float(pos)))
            title = run_script(Command.Get_Current_Song_Title)
            now_playing = f"{title} • {pos}"
            # self.title = now_playing

            self.menu_current.title = now_playing

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

    def clear_discord_status(self):
        self.last_discord_update_was_clear = True
        self.RPC.clear()

    def update_discord_status(self):
        self.last_discord_update_was_clear = False
        try:
            # album = run_script(Command.Get_Current_Song_Album)
            artist = run_script(Command.Get_Current_Song_Artist)
            song = run_script(Command.Get_Current_Song_Title)
            position = run_script_float(Command.Get_Player_Position)

            finish = run_script_float(Command.Get_Current_Song_Finish) - position
            start = run_script_float(Command.Get_Current_Song_Start) - position
            duration = finish - start

            self.RPC.update(
                activity_type=ActivityType.LISTENING,
                details=f"{song}",
                state=f"{artist}",
                large_image=DISCORD_ICON,
                start=time.time() - int(position),
                end=time.time() + int(duration) - int(position),
                small_text="Listening to Apple Music",
            )
        except Exception as e:
            print(e)

        # print(f"Album: {album}")
        # print(f"Artist: {artist}")
        # print(f"Song: {song}")
