"""User preferences persisted as JSON in ~/.music-bar/settings.json."""

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path.home() / ".music-bar" / "settings.json"


@dataclass
class Settings:
    show_discord_status: bool = True
    show_song_in_menu_bar: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Load settings, falling back to defaults for a missing or unreadable file and for unknown/invalid keys."""
        path = path or SETTINGS_PATH
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            logger.exception(f"Could not read settings from {path}; using defaults")
            return cls()

        if not isinstance(data, dict):
            logger.warning(f"Ignoring settings file {path}: expected an object")
            return cls()

        defaults = cls()
        values = {}
        for field in fields(cls):
            value = data.get(field.name, getattr(defaults, field.name))
            if not isinstance(value, type(getattr(defaults, field.name))):
                logger.warning(f"Ignoring invalid value {value!r} for setting {field.name}")
                value = getattr(defaults, field.name)
            values[field.name] = value
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2) + "\n")
            tmp.replace(path)  # atomic, so a crash mid-write can't leave a corrupt file
        except OSError:
            logger.exception(f"Could not save settings to {path}")
