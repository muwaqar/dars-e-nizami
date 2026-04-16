"""
config.py - Playlist mappings and configuration.

Config is loaded from config.json by default.
Use load_config() to load from a custom path.
"""

import json
import re
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
        raw_config = json.load(f)

    _config = _migrate_config(raw_config)
    return _config


def _migrate_config(raw_config: dict) -> dict:
    """
    Migrate old 'subjects' format to new 'playlists' format.
    Old format:
        "subjects": {"Sharh Jami": {"playlist": "PL...", "parts": 5}}
    New format:
        "playlists": [{"filename_key": "Sharh Jami", "yt_video_prefix": "Sharh Jami", "yt_playlist_id": "PL...", "parts": 5}]

    Also migrates recordings_path: old configs default to "Recordings" if not specified.
    """
    if "playlists" in raw_config:
        return raw_config

    if "subjects" in raw_config:
        playlists = []
        for name, info in raw_config["subjects"].items():
            playlists.append(
                {
                    "filename_key": name,
                    "parts": info.get("parts"),
                    "yt_video_prefix": name,
                    "yt_playlist_id": info["playlist"],
                    "yt_playlist_sort": "asc",
                }
            )
        raw_config["playlists"] = playlists
        del raw_config["subjects"]

    if "recordings_path" not in raw_config:
        raw_config["recordings_path"] = "Recordings"

    return raw_config


def get_config_path() -> Optional[Path]:
    """Get the path to the loaded config file."""
    return _config_path


def get_config() -> dict:
    """Get the current configuration. Loads from default path if not loaded."""
    global _config
    if _config is None:
        load_config()
    return _config


def get_playlists() -> list[dict]:
    """Get playlists configuration from config."""
    return get_config().get("playlists", [])


def get_playlist_by_index(index: int) -> Optional[dict]:
    """Get playlist config by index."""
    playlists = get_playlists()
    if 0 <= index < len(playlists):
        return playlists[index]
    return None


def get_recordings_path() -> Path:
    """
    Get recordings path from config.
    Resolves relative to config.json location.
    If recordings_path not specified, defaults to config.json directory (new behavior).
    """
    config_path = get_config_path()
    config_dir = config_path.parent if config_path else Path.cwd()

    recordings = get_config().get("recordings_path")
    if recordings:
        return (config_dir / recordings).expanduser().resolve()
    return config_dir


def get_default_privacy() -> str:
    """Get default privacy status from config."""
    return get_config().get("default_privacy", "unlisted")


def find_playlist_for_file(filename: str) -> Optional[dict]:
    """
    Find matching playlist for a given filename.
    Iterates playlists in order:
    - First playlist with matching filename_key (filename contains it) → use it
    - If no match and only one playlist → use as fallback
    - If no match and multiple playlists → return None (caller should handle error)
    """
    playlists = get_playlists()
    if not playlists:
        return None

    matching_playlists = []
    fallback_playlist = None

    for playlist in playlists:
        filename_key = playlist.get("filename_key")
        if filename_key:
            if filename_key in filename:
                return playlist
        else:
            fallback_playlist = playlist

    if fallback_playlist and len(playlists) == 1:
        return fallback_playlist

    return None


def get_yt_playlist_id(playlist: dict) -> str:
    """Get YouTube playlist ID from playlist config."""
    return playlist["yt_playlist_id"]


def get_yt_video_prefix(playlist: dict) -> str:
    """Get YouTube video prefix from playlist config."""
    return playlist["yt_video_prefix"]


def get_yt_playlist_sort(playlist: dict) -> str:
    """Get playlist sort order. Default is 'asc'."""
    return playlist.get("yt_playlist_sort", "asc")


def get_parts(playlist: dict) -> Optional[int]:
    """Get number of parts from playlist config."""
    return playlist.get("parts")


def parse_filename(filename: str) -> tuple[str, str | None]:
    """
    Parse filename like '1. Sharh Jami 1.mp4' into (prefix_with_part, part_number).
    Returns (prefix, part) where part is None if no part number.

    Examples:
        '1. Sharh Jami 1.mp4'  → ('Sharh Jami 1', '1')
        '8. Maqamaat.mp4'      → ('Maqamaat', None)
        '3. Nur ul Anwar 2.mp4' → ('Nur ul Anwar 2', '2')
    """
    filename = filename.removesuffix(".mp4")
    match = re.match(r"^\d+\.\s+(.+)$", filename)
    if not match:
        raise ValueError(f"Cannot parse filename: {filename}")

    prefix_part = match.group(1).strip()

    match = re.match(r"^(.+?)\s+(\d+)$", prefix_part)
    if match:
        prefix = match.group(1).strip()
        part = match.group(2)
    else:
        prefix = prefix_part
        part = None

    return prefix, part


def get_part_from_filename(filename: str) -> str | None:
    """Extract part number from filename. Returns None if no part."""
    try:
        _, part = parse_filename(filename)
        return part
    except ValueError:
        return None


def generate_title(yt_video_prefix: str, part: str | None, date: str) -> str:
    """
    Generate YouTube title from prefix, part, and date.

    Examples:
        ('Sharh Jami', '1', '2026-04-11') → 'Sharh Jami 1: 2026-04-11'
        ('Maqamaat', None, '2026-04-11')  → 'Maqamaat: 2026-04-11'
    """
    if part:
        return f"{yt_video_prefix} {part}: {date}"
    else:
        return f"{yt_video_prefix}: {date}"


def get_prefix_from_title(title: str) -> str:
    """
    Extract prefix from a YouTube title like 'Sharh Jami 1: 2026-04-11'.
    Returns 'Sharh Jami' (without the part number).
    """
    match = re.match(r"^(.+?)\s*\d*:\s*\d{4}-\d{2}-\d{2}$", title)
    if match:
        prefix = match.group(1).strip()
        if prefix.endswith(":"):
            prefix = prefix[:-1].strip()
        return prefix

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
    match = re.search(r"(\d{4}-\d{2}-\d{2})", title)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract date from title: {title}")


def video_sort_key(title: str, sort_order: str = "asc") -> tuple:
    """
    Generate sort key for a video title based on sort_order.

    For 'asc' (default): sorts by part number (asc), then date (asc).
    Videos without part numbers sort last.

    For 'desc': sorts by date only (descending).

    Returns: tuple for sorting
    """
    date = get_date_from_title(title)

    if sort_order == "desc":
        return (date,)

    part = get_part_from_title(title)

    if part is None:
        part_sort = float("inf")
    else:
        part_sort = int(part)

    return (part_sort, date)


def prefix_matches(prefix1: str, prefix2: str) -> bool:
    """Check if two prefix strings refer to the same item."""
    return prefix1.strip().lower() == prefix2.strip().lower()


def get_client_secrets_file() -> str:
    """Get default client secrets file path. Looks in config directory."""
    config_path = get_config_path()
    if config_path:
        config_dir = config_path.parent
        secrets_path = config_dir / "client_secret.json"
        if secrets_path.exists():
            return str(secrets_path)
    cwd_secret = Path.cwd() / "client_secret.json"
    if cwd_secret.exists():
        return str(cwd_secret)
    raise FileNotFoundError(
        "client_secret.json not found. Use --credentials to specify a custom path."
    )
