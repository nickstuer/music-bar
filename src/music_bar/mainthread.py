"""Hand work from background threads back to the main (UI) thread."""

from collections.abc import Callable

from AppKit import NSRunLoopCommonModes
from Foundation import NSObject


class _MainThreadCall(NSObject):
    """Runs a Python callable on the main thread."""

    def run_(self, _) -> None:  # noqa: ANN001
        self.fn()


def call_on_main(fn: Callable[[], None]) -> None:
    """Schedule ``fn`` on the main thread in all common run loop modes.

    ``AppHelper.callAfter`` only fires in the default mode, so it would wait until a modal dialog or an open menu
    closed; common modes include the modal-panel and menu-tracking modes, so updates show up immediately.
    """
    call = _MainThreadCall.alloc().init()
    call.fn = fn
    call.performSelectorOnMainThread_withObject_waitUntilDone_modes_("run:", None, False, [NSRunLoopCommonModes])  # noqa: FBT003
