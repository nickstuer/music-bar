from enum import Enum

from osascript import osascript


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
    Play_Playlist_From_Name = "play playlist \"{}\""
    Search_Playlist_Name_For_Song = "search playlist {} for \"{}\""
    Get_Playlist_Count = "count playlist"
    Get_Playlist_Name_From_Index = "get name of playlist {}"
    Get_Current_Song_Title = "get name of current track"
    Get_Current_Song_Artist = "get artist of current track"
    Get_Current_Song_Album = "get album of current track"
    Get_Player_Position = "get player position"
    Get_Current_Song_Start = "get start of current track"
    Get_Current_Song_Finish = "get finish of current track"

    def __int__(self):
        return int(self.value)


def run_script(command: Command, *args) -> str:
    command = f"tell application \"Music\" to {command.value.format(*args)}"
    result = osascript(command)[1]
    return result

def run_script_int(command: Command, *args) -> str:
    result = run_script(command, *args)
    return int(result)

def run_script_float(command: Command, *args) -> str:
    result = run_script(command, *args)
    result = result.replace(',', '.')
    return float(result)