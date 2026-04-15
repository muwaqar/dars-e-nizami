"""
config.py - Playlist mappings and subject configuration.

Config is loaded from config.json by default.
Use load_config() to load from a custom path.
"""

import json
from pathlib import Path
from typing import Optional

SCOPES = ["https://www.googleapis.com/auth/youtube"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

_config: Optional[dict] = None
_config_path: Optional[Path] = None


def load_config(config_path: str = "config.json") -> dict:
    """Load configuration from JSON file."""
    global _config, _config_path
    _config_path = Path(config_path).expanduser().resolve()
    with open(_config_path) as f:
        _config = json.load(f)
    return _config


def get_config_path() -> Optional[Path]:
    """Get the path to the loaded config file."""
    return _config_path


def get_config() -> dict:
    """Get the current configuration. Loads from default path if not loaded."""
    global _config
    if _config is None:
        load_config()
    return _config


def get_playlists() -> dict:
    """Get playlist mappings from config."""
    return get_config()["playlists"]


def get_recordings_path() -> Path:
    """
    Get recordings path from config.
    Resolves relative to config.json location, defaults to 'Recordings'.
    """
    config_path = get_config_path()
    config_dir = config_path.parent if config_path else Path.cwd()

    recordings = get_config().get("recordings_path", "Recordings")
    return (config_dir / recordings).expanduser().resolve()


def get_default_privacy() -> str:
    """Get default privacy status from config."""
    return get_config().get("default_privacy", "unlisted")


PLAYLISTS = property(lambda self: get_playlists())
RECORDINGS_PATH = property(lambda self: get_recordings_path())
DEFAULT_PRIVACY = property(lambda self: get_default_privacy())


def parse_filename(filename: str) -> tuple[str, str | None]:
    """
    Parse filename like '1. Sharh Jami 1.mp4' into (subject_with_part, part_number).
    Returns (subject, part) where part is None if no part number.

    Examples:
        '1. Sharh Jami 1.mp4'  → ('Sharh Jami 1', '1')
        '8. Maqamaat.mp4'      → ('Maqamaat', None)
        '3. Nur ul Anwar 2.mp4' → ('Nur ul Anwar 2', '2')
    """
    import re

    filename = filename.removesuffix(".mp4")
    match = re.match(r"^\d+\.\s+(.+)$", filename)
    if not match:
        raise ValueError(f"Cannot parse filename: {filename}")

    subject_part = match.group(1).strip()

    match = re.match(r"^(.+?)\s+(\d+)$", subject_part)
    if match:
        subject = match.group(1).strip()
        part = match.group(2)
    else:
        subject = subject_part
        part = None

    return subject, part


def generate_title(subject: str, part: str | None, date: str) -> str:
    """
    Generate YouTube title from subject, part, and date.

    Examples:
        ('Sharh Jami', '1', '2026-04-11') → 'Sharh Jami 1: 2026-04-11'
        ('Maqamaat', None, '2026-04-11')  → 'Maqamaat: 2026-04-11'
    """
    if part:
        return f"{subject} {part}: {date}"
    else:
        return f"{subject}: {date}"


def get_subject_from_title(title: str) -> str:
    """
    Extract subject from a YouTube title like 'Sharh Jami 1: 2026-04-11'.
    Returns 'Sharh Jami' (without the part number).
    """
    import re

    match = re.match(r"^(.+?)\s*\d*:\s*\d{4}-\d{2}-\d{2}$", title)
    if match:
        subject = match.group(1).strip()
        if subject.endswith(":"):
            subject = subject[:-1].strip()
        return subject

    match = re.match(r"^(.+?):\s*\d{4}-\d{2}-\d{2}$", title)
    if match:
        return match.group(1).strip()

    return title


def get_part_from_title(title: str) -> str | None:
    """
    Extract part number from a YouTube title.

    Examples:
        'Sharh Jami 1: 2026-04-11' → '1'
        'Maqamaat: 2026-04-11'     → None
    """
    import re

    match = re.search(r"\s(\d+):\s*\d{4}-", title)
    if match:
        return match.group(1)
    return None


def get_date_from_title(title: str) -> str:
    """
    Extract date from a YouTube title.

    Example:
        'Sharh Jami 1: 2026-04-11' → '2026-04-11'
    """
    import re

    match = re.search(r"(\d{4}-\d{2}-\d{2})", title)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract date from title: {title}")


def video_sort_key(title: str) -> tuple:
    """
    Generate sort key for a video title.
    Sorts by: part number (asc), then date (asc).
    Videos without part numbers sort by date only (placed appropriately).

    Returns: (part_sort_value, date)
    where part_sort_value is part number as int, or infinity if no part.
    """
    part = get_part_from_title(title)
    date = get_date_from_title(title)

    if part is None:
        part_sort = float("inf")
    else:
        part_sort = int(part)

    return (part_sort, date)


def subject_matches(subject1: str, subject2: str) -> bool:
    """Check if two subject strings refer to the same subject."""
    return subject1.strip().lower() == subject2.strip().lower()
