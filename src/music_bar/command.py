import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def osascript(script: str) -> tuple[int, str, str]:
    """Run an AppleScript and return (returncode, stdout, stderr) with output stripped."""
    proc = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, check=False)  # noqa: S603
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


class Command(Enum):
    Play = "play"
    Pause = "pause"
    Next = "next track"
    Stop = "stop"
    Previous = "previous track"
    Restart = "set player position to 0"
    Get_Player_State = "get player state"
    Get_Volume = "get sound volume"
    Set_Volume = "set sound volume to {}"
    Play_Song_From_ID = "play track id {}"
    Play_Playlist_From_Name = "play playlist {}"
    Get_Playlist_Count = "count playlist"
    Get_Playlist_Name_From_Index = "get name of playlist {}"
    Get_Current_Song_Title = "get name of current track"
    Get_Current_Song_Artist = "get artist of current track"
    Get_Current_Song_Album = "get album of current track"
    Get_Player_Position = "get player position"
    Get_Current_Song_Start = "get start of current track"
    Get_Current_Song_Finish = "get finish of current track"


_NO_DEFAULT = object()


def run_script[T](  # noqa: ANN201
    command: Command,
    *args,  # noqa: ANN002
    converter: Callable[[str], T] = str,
    default: object = _NO_DEFAULT,
):
    """Run a Music command. If ``default`` is given, it is returned when the output can't be converted.

    Music returns empty output when it is quitting or has no current track, which would otherwise make
    ``int("")``/``float("")`` raise.
    """
    command_text = f'tell application "Music" to {command.value.format(*args)}'
    result = osascript(command_text)[1]
    if converter is float:
        result = result.replace(",", ".")
    try:
        return converter(result)
    except ValueError:
        if default is _NO_DEFAULT:
            raise
        logger.warning(f"Unexpected output {result!r} for {command.name}; using {default!r}")
        return default


def applescript_string(text: str) -> str:
    """Quote text as an AppleScript string literal so user input can't break out of it."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class Track:
    track_id: int
    name: str
    artist: str


SEARCH_LIBRARY_SCRIPT = """
tell application "Music"
    set found to search library playlist 1 for {query}
    set output to ""
    repeat with i from 1 to (count of found)
        if i > {limit} then exit repeat
        set t to item i of found
        set output to output & (id of t) & tab & (name of t) & tab & (artist of t) & linefeed
    end repeat
    return output
end tell
"""


def search_library(query: str, limit: int = 25) -> list[Track]:
    """Search the whole Music library once and return up to ``limit`` matching tracks."""
    output = run_raw_script(SEARCH_LIBRARY_SCRIPT.format(query=applescript_string(query), limit=limit))
    tracks = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].isdigit():  # noqa: PLR2004
            continue
        tracks.append(Track(int(parts[0]), parts[1], parts[2]))
    return tracks


def run_raw_script(command: str) -> str:
    return osascript(command)[1]


PLAYLIST_NAMES_SCRIPT = """
tell application "Music"
    set output to ""
    repeat with p in playlists
        set output to output & (name of p) & linefeed
    end repeat
    return output
end tell
"""


def get_playlist_names() -> list[str]:
    """Return every playlist name in a single AppleScript call."""
    return [name for name in run_raw_script(PLAYLIST_NAMES_SCRIPT).splitlines() if name.strip()]
