"""Coalescing, rate-limited sender for values that change faster than they can be applied."""

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_UNSET = object()


class LatestValueSender[T]:
    """Sends only the most recent submitted value, at most once per ``min_interval`` seconds.

    Sending happens on a background thread so slow sends (e.g. spawning ``osascript``) never block the caller.
    Values submitted while a send is in flight or during the cooldown replace each other; the latest one is always
    sent eventually.
    """

    def __init__(self, send: Callable[[T], object], min_interval: float = 0.1) -> None:
        self._send = send
        self._min_interval = min_interval
        self._pending: object = _UNSET
        self._last_submit = 0.0
        self._condition = threading.Condition()
        self._thread = threading.Thread(target=self._run, name="LatestValueSender", daemon=True)
        self._thread.start()

    def submit(self, value: T) -> None:
        with self._condition:
            self._pending = value
            self._last_submit = time.monotonic()
            self._condition.notify()

    def seconds_since_submit(self) -> float:
        with self._condition:
            return time.monotonic() - self._last_submit

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is _UNSET:
                    self._condition.wait()
                value, self._pending = self._pending, _UNSET

            try:
                self._send(value)
            except Exception:
                logger.exception("Failed to send value")

            time.sleep(self._min_interval)
