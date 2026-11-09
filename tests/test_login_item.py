import sys
from unittest.mock import MagicMock, patch

from music_bar import login_item


def service_mock(*, ok=True, error=None, status=0):
    service = MagicMock()
    service.registerAndReturnError_.return_value = (ok, error)
    service.unregisterAndReturnError_.return_value = (ok, error)
    service.status.return_value = status
    return patch.object(login_item, "SMAppService", MagicMock(mainAppService=MagicMock(return_value=service))), service


def test_supported_only_when_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not login_item.is_supported()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert login_item.is_supported()


def test_enable_and_disable():
    patcher, service = service_mock()
    with patcher:
        assert login_item.set_enabled(True) is None
        service.registerAndReturnError_.assert_called_once_with(None)
        assert login_item.set_enabled(False) is None
        service.unregisterAndReturnError_.assert_called_once_with(None)


def test_error_message_returned():
    error = MagicMock()
    error.localizedDescription.return_value = "Operation not permitted"
    patcher, _ = service_mock(ok=False, error=error)
    with patcher:
        assert login_item.set_enabled(True) == "Operation not permitted"


def test_status_checks():
    patcher, _ = service_mock(status=login_item.SMAppServiceStatusEnabled)
    with patcher:
        assert login_item.is_enabled()
        assert not login_item.needs_approval()
    patcher, _ = service_mock(status=login_item.SMAppServiceStatusRequiresApproval)
    with patcher:
        assert not login_item.is_enabled()
        assert login_item.needs_approval()
