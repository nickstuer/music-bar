from music_bar.player import PlaybackClock, PlayerInfoObserver


class FakeTime:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_clock_advances_while_running():
    fake = FakeTime()
    clock = PlaybackClock(now=fake)
    clock.sync(30.0, running=True)
    fake.now += 5
    assert clock.position() == 35.0
    assert clock.seconds_since_sync() == 5


def test_clock_frozen_while_paused():
    fake = FakeTime()
    clock = PlaybackClock(now=fake)
    clock.sync(30.0, running=False)
    fake.now += 5
    assert clock.position() == 30.0


def test_pausing_keeps_extrapolated_position():
    fake = FakeTime()
    clock = PlaybackClock(now=fake)
    clock.sync(10.0, running=True)
    fake.now += 3
    clock.sync(clock.position(), running=False)
    fake.now += 50
    assert clock.position() == 13.0


class FakeNotification:
    def __init__(self, info):
        self._info = info

    def userInfo(self):  # noqa: N802
        return self._info


def test_observer_forwards_user_info():
    received = []
    observer = PlayerInfoObserver.alloc().initWithCallback_(received.append)
    observer.playerInfoChanged_(FakeNotification({"Player State": "Playing", "Name": "Song"}))
    assert received == [{"Player State": "Playing", "Name": "Song"}]


def test_observer_swallows_callback_errors():
    def boom(_):
        raise RuntimeError

    observer = PlayerInfoObserver.alloc().initWithCallback_(boom)
    observer.playerInfoChanged_(FakeNotification({}))  # must not raise
