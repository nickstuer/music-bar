"""Launch at login via SMAppService (macOS 13+).

SMAppService registers the *app bundle* that is running, so this only works in the built Music Bar.app. When running
from source the "app" would be the Python interpreter, so the option is shown but disabled.
"""

import logging
import sys

from ServiceManagement import SMAppService, SMAppServiceStatusEnabled, SMAppServiceStatusRequiresApproval

logger = logging.getLogger(__name__)


def is_supported() -> bool:
    """Return whether this is the PyInstaller-built app bundle, the only build that can register itself."""
    return bool(getattr(sys, "frozen", False))


def is_enabled() -> bool:
    return SMAppService.mainAppService().status() == SMAppServiceStatusEnabled


def needs_approval() -> bool:
    """Return whether it is registered but still needs allowing in System Settings > General > Login Items."""
    return SMAppService.mainAppService().status() == SMAppServiceStatusRequiresApproval


def set_enabled(enabled: bool) -> str | None:  # noqa: FBT001
    """Register or unregister the app as a login item. Returns an error message, or None on success."""
    service = SMAppService.mainAppService()
    if enabled:
        ok, error = service.registerAndReturnError_(None)
    else:
        ok, error = service.unregisterAndReturnError_(None)
    if ok:
        logger.info(f"Launch at login {'enabled' if enabled else 'disabled'}")
        return None
    message = str(error.localizedDescription()) if error is not None else "Unknown error"
    logger.error(f"Failed to {'enable' if enabled else 'disable'} launch at login: {message}")
    return message


def open_login_items_settings() -> None:
    SMAppService.openSystemSettingsLoginItems()
