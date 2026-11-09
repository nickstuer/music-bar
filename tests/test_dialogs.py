from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from music_bar import dialogs


@contextmanager
def patched_app(app):
    """Swap the module's NSApplication and run loop for mocks (PyObjC class methods can't be patched directly)."""
    ns_application = MagicMock()
    ns_application.sharedApplication.return_value = app
    with patch.object(dialogs, "NSApplication", ns_application), patch.object(dialogs, "NSRunLoop", MagicMock()):
        yield


def fake_app(*, active=False, has_legacy=True):
    app = MagicMock()
    state = {"active": active}
    app.isActive.side_effect = lambda: state["active"]
    app.respondsToSelector_.side_effect = lambda sel: has_legacy and sel == "activateIgnoringOtherApps:"

    def become_active(*_: object) -> None:
        state["active"] = True

    app.activateIgnoringOtherApps_.side_effect = become_active
    app.activate.side_effect = become_active
    return app


def test_activate_noop_when_already_active():
    app = fake_app(active=True)
    with patched_app(app):
        dialogs.activate_app()
    app.activateIgnoringOtherApps_.assert_not_called()
    app.activate.assert_not_called()


def test_activate_prefers_forced_activation():
    app = fake_app()
    with patched_app(app):
        dialogs.activate_app()
    app.activateIgnoringOtherApps_.assert_called_once_with(True)  # noqa: FBT003
    app.activate.assert_not_called()


def test_activate_falls_back_when_legacy_api_removed():
    app = fake_app(has_legacy=False)
    with patched_app(app):
        dialogs.activate_app()
    app.activate.assert_called_once()


def test_activate_gives_up_after_timeout():
    app = fake_app()
    app.activateIgnoringOtherApps_.side_effect = None  # activation never happens
    with patched_app(app), patch.object(dialogs, "ACTIVATION_TIMEOUT", 0.05):
        dialogs.activate_app()  # returns instead of hanging


def test_show_alert_activates_first():
    calls = []
    with (
        patch.object(dialogs, "activate_app", side_effect=lambda: calls.append("activate")),
        patch.object(dialogs.rumps, "alert", side_effect=lambda *_, **__: calls.append("alert")),
    ):
        dialogs.show_alert("Title", "Message")
    assert calls == ["activate", "alert"]


# --- Live search -------------------------------------------------------------------------------------------------

TRACKS = [dialogs.Track(1, "One", "A"), dialogs.Track(2, "Two", "B"), dialogs.Track(3, "Three", "C")]


class SyncSender:
    """Runs searches immediately instead of on a background thread."""

    def __init__(self, send, **_: object):
        self.send = send
        self.submitted = []
        self.stopped = False

    def submit(self, value):
        self.submitted.append(value)
        self.send(value)

    def stop(self):
        self.stopped = True


class FakeTable:
    def __init__(self):
        self.row = -1
        self.reloads = 0

    def reloadData(self):  # noqa: N802
        self.reloads += 1

    def selectRowIndexes_byExtendingSelection_(self, indexes, _extend):  # noqa: N802
        self.row = indexes.firstIndex()

    def scrollRowToVisible_(self, _row):  # noqa: N802
        pass

    def selectedRow(self):  # noqa: N802
        return self.row


def make_controller(search=lambda _: TRACKS, dispatch=lambda fn: fn()):
    table, status = FakeTable(), MagicMock()
    controller = (
        dialogs.LiveSearchController.alloc()
        .init()
        .configure(search, table, status, dispatch=dispatch, sender_factory=SyncSender)
    )
    return controller, table, status


def last_status(status):
    return status.setStringValue_.call_args[0][0]


def test_typing_shows_results_and_selects_first():
    controller, table, status = make_controller()
    controller.query_changed("o")
    assert controller.tracks == TRACKS
    assert controller.numberOfRowsInTableView_(table) == 3
    assert controller.tableView_objectValueForTableColumn_row_(table, None, 1) == "Two — B"
    assert controller.selected_track() == TRACKS[0]
    assert "3 songs" in last_status(status)


def test_same_query_is_not_searched_twice():
    controller, _, _ = make_controller()
    controller.query_changed("one")
    controller.query_changed(" one ")  # e.g. controlTextDidChange_ and the field action both fire
    assert controller.searcher.submitted == ["one"]


def test_clearing_the_field_clears_results():
    controller, _, status = make_controller()
    controller.query_changed("o")
    controller.query_changed("")
    assert controller.tracks == []
    assert controller.selected_track() is None
    assert last_status(status) == "Type to search your library."


def test_stale_results_are_ignored():
    pending = []
    controller, _, _ = make_controller(dispatch=pending.append)
    controller.query_changed("o")
    controller.query_changed("on")
    pending[0]()  # results for "o" arrive after the user typed "on"
    assert controller.tracks == []
    pending[1]()
    assert controller.tracks == TRACKS


def test_no_results_message():
    controller, _, status = make_controller(search=lambda _: [])
    controller.query_changed("zzz")
    assert last_status(status) == "No results for “zzz”."


def test_search_errors_show_no_results():
    def broken(_):
        raise RuntimeError

    controller, _, status = make_controller(search=broken)
    controller.query_changed("x")
    assert controller.tracks == []
    assert "No results" in last_status(status)


def test_arrow_keys_move_selection_within_bounds():
    controller, table, _ = make_controller()
    controller.query_changed("o")
    assert controller.control_textView_doCommandBySelector_(None, None, "moveDown:")
    assert controller.selected_track() == TRACKS[1]
    controller.control_textView_doCommandBySelector_(None, None, "moveDown:")
    controller.control_textView_doCommandBySelector_(None, None, "moveDown:")
    assert table.row == 2
    for _ in range(5):
        controller.control_textView_doCommandBySelector_(None, None, "moveUp:")
    assert table.row == 0


def test_other_keys_are_left_to_the_field():
    controller, _, _ = make_controller()
    assert not controller.control_textView_doCommandBySelector_(None, None, "deleteBackward:")


def test_return_plays_selected_and_escape_cancels():
    controller, _, _ = make_controller()
    controller.query_changed("o")
    app = MagicMock()
    with patch.object(dialogs, "NSApplication", MagicMock(sharedApplication=MagicMock(return_value=app))):
        controller.control_textView_doCommandBySelector_(None, None, b"insertNewline:")
        app.stopModalWithCode_.assert_called_once_with(dialogs.NSAlertFirstButtonReturn)
        app.reset_mock()
        controller.control_textView_doCommandBySelector_(None, None, "cancelOperation:")
        app.stopModalWithCode_.assert_called_once_with(dialogs.NSAlertSecondButtonReturn)


def test_return_without_results_does_nothing():
    controller, _, _ = make_controller(search=lambda _: [])
    controller.query_changed("zzz")
    app = MagicMock()
    with patch.object(dialogs, "NSApplication", MagicMock(sharedApplication=MagicMock(return_value=app))):
        controller.control_textView_doCommandBySelector_(None, None, "insertNewline:")
    app.stopModalWithCode_.assert_not_called()


def test_close_stops_search_thread():
    controller, _, _ = make_controller()
    controller.close()
    assert controller.searcher.stopped


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "1 song."), (2, "2 songs."), (dialogs.MAX_RESULTS, f"{dialogs.MAX_RESULTS}+ songs.")],
)
def test_status_text_counts(count, expected):
    assert dialogs.status_text("q", count).startswith(expected)


def test_search_dialog_builds_layout_without_showing():
    captured = {}

    def fake_run_modal(alert, first_responder=None):
        captured["alert"], captured["field"] = alert, first_responder
        return False

    with patch.object(dialogs, "_run_modal", side_effect=fake_run_modal):
        assert dialogs.search_dialog(lambda _: TRACKS) is None

    container = captured["alert"].accessoryView()
    field, scroll, status = container.subviews()
    assert captured["field"] is field
    assert field.delegate() is not None
    table = scroll.documentView()
    row = table.rowHeight() + table.intercellSpacing().height
    assert scroll.frame().size.height == dialogs.VISIBLE_ROWS * row
    assert scroll.hasVerticalScroller()
    assert scroll.autohidesScrollers()
    assert field.frame().origin.y > scroll.frame().origin.y > status.frame().origin.y


def test_objc_callback_signatures():
    cls = dialogs.LiveSearchController
    assert cls.control_textView_doCommandBySelector_.signature.startswith(b"Z")  # returns BOOL
    assert cls.numberOfRowsInTableView_.signature.startswith(b"q")  # returns NSInteger
    assert cls.tableView_objectValueForTableColumn_row_.signature.endswith(b"q")  # row is NSInteger
