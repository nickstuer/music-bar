"""Native dialogs that rumps doesn't provide."""

import logging
import time
from collections.abc import Callable

import objc
import rumps
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSApplication,
    NSBezelBorder,
    NSColor,
    NSDate,
    NSDefaultRunLoopMode,
    NSFont,
    NSImage,
    NSIndexSet,
    NSLineBreakByTruncatingTail,
    NSMakeRect,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSScrollView,
    NSSearchField,
    NSTableColumn,
    NSTableView,
    NSTableViewStylePlain,
    NSTableViewUniformColumnAutoresizingStyle,
    NSTextField,
    NSView,
)
from Foundation import NSObject

from .command import Track
from .throttle import LatestValueSender

logger = logging.getLogger(__name__)

ACTIVATION_TIMEOUT = 0.3

# Live search window
MAX_RESULTS = 50
VISIBLE_ROWS = 10
SEARCH_MIN_INTERVAL = 0.05
SEARCH_WIDTH = 380
ROW_HEIGHT = 20
FIELD_HEIGHT = 24
STATUS_HEIGHT = 16
GAP = 6


def activate_app() -> None:
    """Bring Music Bar to the front so its dialogs appear above other apps and receive keyboard input.

    Menu bar apps aren't active by default, so a modal dialog opened from the menu can appear behind the current app
    and keystrokes keep going to that app.

    ``activateIgnoringOtherApps_`` is deprecated since macOS 14, but its replacement ``activate`` uses "cooperative
    activation" and is refused when another app is frontmost, which is exactly the case here. The deprecated call
    still works (verified on macOS 27), so prefer it and fall back to ``activate`` if it's ever removed.
    """
    app = NSApplication.sharedApplication()
    if app.isActive():
        return
    if app.respondsToSelector_("activateIgnoringOtherApps:"):
        app.activateIgnoringOtherApps_(True)  # noqa: FBT003
    else:
        app.activate()

    # Activation is asynchronous; give it a moment so the dialog becomes the key window when it opens.
    deadline = time.monotonic() + ACTIVATION_TIMEOUT
    while not app.isActive() and time.monotonic() < deadline:
        NSRunLoop.currentRunLoop().runMode_beforeDate_(NSDefaultRunLoopMode, NSDate.dateWithTimeIntervalSinceNow_(0.01))


def _new_alert(title: str, message: str, buttons: list[str], icon_path: str | None) -> NSAlert:
    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    for button in buttons:
        alert.addButtonWithTitle_(button)
    if icon_path:
        icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if icon is not None:
            alert.setIcon_(icon)
    return alert


def _run_modal(alert: NSAlert, first_responder: object = None) -> bool:
    """Show the alert in front of everything, focused. Returns True if the first button was clicked."""
    activate_app()
    if first_responder is not None:
        alert.layout()
        alert.window().setInitialFirstResponder_(first_responder)
        alert.window().makeFirstResponder_(first_responder)
    return alert.runModal() == NSAlertFirstButtonReturn


def show_alert(title: str, message: str = "", icon_path: str | None = None) -> None:
    """``rumps.alert`` that is guaranteed to appear in front."""
    activate_app()
    rumps.alert(title, message, icon_path=icon_path)


class _MainThreadCall(NSObject):
    """Runs a Python callable on the main thread."""

    def run_(self, _) -> None:  # noqa: ANN001
        self.fn()


def call_on_main(fn: Callable[[], None]) -> None:
    """Schedule ``fn`` on the main thread in all common run loop modes.

    ``AppHelper.callAfter`` only fires in the default mode, so it would wait until a modal dialog closed; common modes
    include the modal-panel mode, so results reach an open dialog immediately.
    """
    call = _MainThreadCall.alloc().init()
    call.fn = fn
    call.performSelectorOnMainThread_withObject_waitUntilDone_modes_("run:", None, False, [NSRunLoopCommonModes])  # noqa: FBT003


def _selector_name(selector: object) -> str:
    return selector.decode() if isinstance(selector, bytes) else str(selector)


def status_text(query: str, count: int) -> str:
    if not query:
        return "Type to search your library."
    if count == 0:
        return f"No results for \u201c{query}\u201d."
    noun = "song" if count == 1 else "songs"
    more = "+" if count >= MAX_RESULTS else ""
    return f"{count}{more} {noun}. \u2191\u2193 to choose, Return to play."


class LiveSearchController(NSObject):
    """Searches as the user types and backs the results table (data source, keyboard navigation)."""

    @objc.python_method
    def configure(
        self,
        search: Callable[[str], list[Track]],
        table: object,
        status: object,
        dispatch: Callable[[Callable[[], None]], None] = call_on_main,
        sender_factory: Callable[..., LatestValueSender] = LatestValueSender,
    ) -> "LiveSearchController":
        self.search = search
        self.table = table
        self.status = status
        self.dispatch = dispatch
        self.tracks: list[Track] = []
        self.query = ""
        # One search in flight at a time; keystrokes typed meanwhile collapse into a single search for the latest text.
        self.searcher = sender_factory(self._search_in_background, min_interval=SEARCH_MIN_INTERVAL)
        self.status.setStringValue_(status_text("", 0))
        return self

    @objc.python_method
    def _search_in_background(self, query: str) -> None:
        try:
            tracks = self.search(query)
        except Exception:
            logger.exception(f"Search failed for {query!r}")
            tracks = []
        self.dispatch(lambda: self.show_results(query, tracks))

    @objc.python_method
    def query_changed(self, text: str) -> None:
        query = text.strip()
        if query == self.query:
            return
        self.query = query
        if not query:
            self.show_results("", [])
            return
        self.status.setStringValue_("Searching\u2026")
        self.searcher.submit(query)

    @objc.python_method
    def show_results(self, query: str, tracks: list[Track]) -> None:
        if query != self.query:
            return  # Results for text the user has already changed.
        self.tracks = tracks
        self.table.reloadData()
        if tracks:
            self.select_row(0)
        self.status.setStringValue_(status_text(query, len(tracks)))

    @objc.python_method
    def select_row(self, row: int) -> None:
        self.table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)  # noqa: FBT003
        self.table.scrollRowToVisible_(row)

    @objc.python_method
    def move_selection(self, delta: int) -> None:
        if not self.tracks:
            return
        row = self.table.selectedRow()
        self.select_row(min(max(row + delta, 0), len(self.tracks) - 1))

    @objc.python_method
    def selected_track(self) -> Track | None:
        row = self.table.selectedRow()
        return self.tracks[row] if 0 <= row < len(self.tracks) else None

    @objc.python_method
    def finish(self, *, play: bool) -> None:
        if play and self.selected_track() is None:
            return
        NSApplication.sharedApplication().stopModalWithCode_(
            NSAlertFirstButtonReturn if play else NSAlertSecondButtonReturn,
        )

    @objc.python_method
    def close(self) -> None:
        self.searcher.stop()

    # NSTableViewDataSource
    def numberOfRowsInTableView_(self, _table) -> int:  # noqa: ANN001, N802
        return len(self.tracks)

    def tableView_objectValueForTableColumn_row_(self, _table, _column, row: int) -> str:  # noqa: ANN001, N802
        track = self.tracks[row]
        return f"{track.name} \u2014 {track.artist}"

    # Search field delegate / action
    def controlTextDidChange_(self, notification) -> None:  # noqa: ANN001, N802
        self.query_changed(str(notification.object().stringValue()))

    def searchFieldChanged_(self, sender) -> None:  # noqa: ANN001, N802
        # Also fires when the field's clear button is clicked, which doesn't send controlTextDidChange_.
        self.query_changed(str(sender.stringValue()))

    def control_textView_doCommandBySelector_(self, _control, _text_view, selector) -> bool:  # noqa: ANN001, N802
        # Keys typed in the search field: arrows move through results, Return plays, Escape cancels.
        name = _selector_name(selector)
        if name == "moveDown:":
            self.move_selection(1)
        elif name == "moveUp:":
            self.move_selection(-1)
        elif name == "insertNewline:":
            self.finish(play=True)
        elif name == "cancelOperation:":
            self.finish(play=False)
        else:
            return False
        return True

    def tableDoubleClicked_(self, _sender) -> None:  # noqa: ANN001, N802
        self.finish(play=True)


def search_dialog(search: Callable[[str], list[Track]], icon_path: str | None = None) -> Track | None:
    """Live-search window: results update while typing. Returns the chosen track, or None if cancelled."""
    alert = _new_alert("Search Music", "Search your library by song, artist or album.", ["Play", "Cancel"], icon_path)

    table = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, SEARCH_WIDTH, 0))
    column = NSTableColumn.alloc().initWithIdentifier_("track")
    column.setWidth_(SEARCH_WIDTH)
    column.setEditable_(False)
    column.dataCell().setLineBreakMode_(NSLineBreakByTruncatingTail)
    table.addTableColumn_(column)
    table.setHeaderView_(None)
    table.setStyle_(NSTableViewStylePlain)
    table.setColumnAutoresizingStyle_(NSTableViewUniformColumnAutoresizingStyle)
    table.setRowHeight_(ROW_HEIGHT)
    table.setUsesAlternatingRowBackgroundColors_(True)

    # Exactly VISIBLE_ROWS rows tall; the scroll bar appears only when there are more results.
    list_height = VISIBLE_ROWS * (table.rowHeight() + table.intercellSpacing().height)
    scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, STATUS_HEIGHT + GAP, SEARCH_WIDTH, list_height))
    scroll.setDocumentView_(table)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setBorderType_(NSBezelBorder)

    field_y = STATUS_HEIGHT + GAP + list_height + GAP
    field = NSSearchField.alloc().initWithFrame_(NSMakeRect(0, field_y, SEARCH_WIDTH, FIELD_HEIGHT))
    field.setPlaceholderString_("Song, artist or album")

    status = NSTextField.labelWithString_("")
    status.setFrame_(NSMakeRect(0, 0, SEARCH_WIDTH, STATUS_HEIGHT))
    status.setTextColor_(NSColor.secondaryLabelColor())
    status.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))

    controller = LiveSearchController.alloc().init().configure(search, table, status)
    table.setDataSource_(controller)
    table.setTarget_(controller)
    table.setDoubleAction_("tableDoubleClicked:")
    field.setDelegate_(controller)
    field.setTarget_(controller)
    field.setAction_("searchFieldChanged:")

    container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, SEARCH_WIDTH, field_y + FIELD_HEIGHT))
    for view in (field, scroll, status):
        container.addSubview_(view)
    alert.setAccessoryView_(container)

    try:
        play = _run_modal(alert, first_responder=field)
        return controller.selected_track() if play else None
    finally:
        controller.close()
