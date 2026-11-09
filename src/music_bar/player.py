"""Event-driven playback tracking for Apple Music.

Music posts the distributed notification ``com.apple.Music.playerInfo`` whenever playback starts, pauses, stops or the
track changes, so we only need to run AppleScript when something actually happens. The playback position is
extrapolated locally between occasional resyncs.
"""

import logging
import time
from collections.abc import Callable

import objc
from AppKit import NSRunningApplication
from Foundation import NSDistributedNotificationCenter, NSObject

logger = logging.getLogger(__name__)

MUSIC_BUNDLE_ID = "com.apple.Music"
PLAYER_INFO_NOTIFICATION = "com.apple.Music.playerInfo"


def is_music_running() -> bool:
    """Check whether Music is running without launching it or spawning a process."""
    return len(NSRunningApplication.runningApplicationsWithBundleIdentifier_(MUSIC_BUNDLE_ID)) > 0


class PlaybackClock:
    """Tracks the playback position from a known anchor point instead of polling Music for it."""

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._position = 0.0
        self._anchored_at = now()
        self.running = False

    def sync(self, position: float, *, running: bool) -> None:
        self._position = position
        self._anchored_at = self._now()
        self.running = running

    def position(self) -> float:
        if not self.running:
            return self._position
        return self._position + (self._now() - self._anchored_at)

    def seconds_since_sync(self) -> float:
        return self._now() - self._anchored_at


class PlayerInfoObserver(NSObject):
    """Forwards Music's playerInfo notifications to a Python callback as a plain dict."""

    def initWithCallback_(self, callback: Callable[[dict], None]) -> "PlayerInfoObserver | None":  # noqa: N802
        self = objc.super(PlayerInfoObserver, self).init()  # noqa: PLW0642
        if self is None:
            return None
        self._callback = callback
        return self

    def playerInfoChanged_(self, notification) -> None:  # noqa: ANN001, N802
        # Exceptions must not escape into Objective-C, where they would crash the app.
        try:
            info = {str(key): value for key, value in (notification.userInfo() or {}).items()}
            self._callback(info)
        except Exception:
            logger.exception("Failed to handle Music playerInfo notification")

    def start(self) -> None:
        NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self,
            "playerInfoChanged:",
            PLAYER_INFO_NOTIFICATION,
            None,
        )

    def stop(self) -> None:
        NSDistributedNotificationCenter.defaultCenter().removeObserver_(self)
