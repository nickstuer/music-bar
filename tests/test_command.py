from unittest.mock import patch

import pytest

from music_bar.command import Command, run_raw_script, run_script


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
