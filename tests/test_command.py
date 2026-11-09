from unittest.mock import patch

import pytest

from music_bar.command import (
    Command,
    Track,
    applescript_string,
    get_playlist_names,
    run_raw_script,
    run_script,
    search_library,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (Command.Play, "play"),
        (Command.Pause, "pause"),
        (Command.Next, "next track"),
        (Command.Get_Current_Song_Title, "get name of current track"),
    ],
)
def test_command_enum_values(command, expected):
    assert expected in command.value


@patch("music_bar.command.osascript")
def test_run_script_str(mock_osascript):
    mock_osascript.return_value = (0, "result")
    result = run_script(Command.Get_Current_Song_Title)
    assert result == "result"
    mock_osascript.assert_called_once()
    called_command = mock_osascript.call_args[0][0]
    assert called_command.startswith('tell application "Music" to get name of current track')


@patch("music_bar.command.osascript")
def test_run_script_with_args(mock_osascript):
    mock_osascript.return_value = (0, "42")
    result = run_script(Command.Set_Volume, 42)
    assert result == "42"
    assert "set sound volume to 42" in mock_osascript.call_args[0][0]


@patch("music_bar.command.osascript")
def test_run_script_converter_int(mock_osascript):
    mock_osascript.return_value = (0, "123")
    result = run_script(Command.Get_Volume, converter=int)
    assert result == 123


@patch("music_bar.command.osascript")
def test_run_script_converter_float(mock_osascript):
    mock_osascript.return_value = (0, "3,14")
    result = run_script(Command.Get_Player_Position, converter=float)
    assert result == 3.14


@patch("music_bar.command.osascript")
def test_run_raw_script(mock_osascript):
    mock_osascript.return_value = (0, "raw_result")
    result = run_raw_script('tell application "Music" to play')
    assert result == "raw_result"
    mock_osascript.assert_called_once_with('tell application "Music" to play')


@patch("music_bar.command.osascript")
def test_run_script_default_on_bad_output(mock_osascript):
    mock_osascript.return_value = (1, "")
    assert run_script(Command.Get_Volume, converter=int, default=7) == 7


@patch("music_bar.command.osascript")
def test_run_script_raises_without_default(mock_osascript):
    mock_osascript.return_value = (1, "")
    with pytest.raises(ValueError):  # noqa: PT011
        run_script(Command.Get_Volume, converter=int)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", '"hello"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ('" & do shell script "rm', '"\\" & do shell script \\"rm"'),
    ],
)
def test_applescript_string_escapes(text, expected):
    assert applescript_string(text) == expected


@patch("music_bar.command.osascript")
def test_search_library_parses_results(mock_osascript):
    mock_osascript.return_value = (0, "12\tSong A\tArtist A\n34\tSong B\tArtist B\n\ngarbage\n")
    assert search_library('q "x"') == [Track(12, "Song A", "Artist A"), Track(34, "Song B", "Artist B")]
    script = mock_osascript.call_args[0][0]
    assert 'search library playlist 1 for "q \\"x\\""' in script


@patch("music_bar.command.osascript")
def test_get_playlist_names_includes_last(mock_osascript):
    mock_osascript.return_value = (0, "Library\nMusic\nWorkout\n")
    assert get_playlist_names() == ["Library", "Music", "Workout"]
