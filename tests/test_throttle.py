import itertools
import threading
import time

from music_bar.throttle import LatestValueSender


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_sends_single_value():
    sent = []
    sender = LatestValueSender(sent.append, min_interval=0.01)
    sender.submit(5)
    assert wait_for(lambda: sent == [5])


def test_coalesces_burst_and_sends_latest():
    sent = []
    release = threading.Event()

    def slow_send(value):
        sent.append(value)
        release.wait(1)

    sender = LatestValueSender(slow_send, min_interval=0.01)
    sender.submit(1)
    assert wait_for(lambda: sent == [1])
    for value in range(2, 50):
        sender.submit(value)
    release.set()
    assert wait_for(lambda: sent[-1] == 49)
    assert sent == [1, 49]


def test_rate_limited():
    times = []
    sender = LatestValueSender(lambda _: times.append(time.monotonic()), min_interval=0.05)
    for value in range(3):
        sender.submit(value)
        time.sleep(0.06)
    assert wait_for(lambda: len(times) == 3)
    gaps = [b - a for a, b in itertools.pairwise(times)]
    assert all(gap >= 0.045 for gap in gaps)


def test_send_errors_do_not_kill_worker():
    sent = []

    def flaky(value):
        if value == 1:
            raise RuntimeError
        sent.append(value)

    sender = LatestValueSender(flaky, min_interval=0.01)
    sender.submit(1)
    time.sleep(0.05)
    sender.submit(2)
    assert wait_for(lambda: sent == [2])


def test_stop_ends_worker_thread():
    sender = LatestValueSender(lambda _: None, min_interval=0.01)
    sender.stop()
    sender._thread.join(1)  # noqa: SLF001
    assert not sender._thread.is_alive()  # noqa: SLF001
