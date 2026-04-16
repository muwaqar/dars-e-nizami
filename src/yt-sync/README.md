# yt-sync

Sync local recordings to YouTube and organize them into playlists.

## Setup

```bash
cd src/yt-sync/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt
```

## Configuration

1. Copy `sample-config.json` to your recordings folder as `config.json`:

```json
{
  "default_privacy": "unlisted",
  "recordings_path": "Recordings",
  "playlists": [
    {
      "filename_key": "Sharh Jami",
      "parts": 3,
      "yt_video_prefix": "Sharh Jami",
      "yt_playlist_id": "PL...",
      "yt_playlist_sort": "asc"
    }
  ]
}
```

2. Place your `client_secret.json` (from Google Cloud Console) in the `src/yt-sync/` directory.

3. On first run, authenticate with YouTube (opens browser).

## Config Fields

| Field | Required | Description |
|-------|----------|-------------|
| `default_privacy` | No | Video privacy: "public", "unlisted", "private" (default: unlisted) |
| `recordings_path` | No | Subdirectory to scan for mp4 files. If omitted, scans same directory as config.json |
| `playlists` | Yes | List of playlist configurations |

### Playlist Fields

| Field | Required | Description |
|-------|----------|-------------|
| `filename_key` | No | Filename must contain this string to match. If omitted, this is the fallback playlist |
| `parts` | No | Number of parts per recording (for sorting) |
| `yt_video_prefix` | Yes | Title prefix for YouTube videos |
| `yt_playlist_id` | Yes | YouTube playlist ID |
| `yt_playlist_sort` | No | Sort order: "asc" (default) or "desc" |

## Usage - Syncer

```bash
cd src/yt-sync/

# Preview mode
python3 syncer.py --config /path/to/config.json --dry-run

# Sync all recordings
python3 syncer.py --config /path/to/config.json

# Sync specific path
python3 syncer.py --config /path/to/config.json --path Section-F

# Verbose output
python3 syncer.py --config /path/to/config.json --verbose

# Re-authenticate (force new OAuth flow)
python3 syncer.py --config /path/to/config.json --re-authenticate
```

## Usage - Cutter

Cut Zoom recordings into individual class segments.

```bash
cd src/yt-sync/

# Interactive mode
python3 cutter.py input.mp4 --config /path/to/config.json

# With destination path
python3 cutter.py input.mp4 --path Section-F/2026-04-11 --config /path/to/config.json

# Preview mode
python3 cutter.py input.mp4 --dry-run --config /path/to/config.json

# Overwrite existing files
python3 cutter.py input.mp4 --overwrite --config /path/to/config.json
```

## CLI Options

### Syncer

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to config file |
| `--credentials PATH` | Path to client_secret.json |
| `--path GLOB` | Filter recordings by path |
| `--dry-run` | Preview without uploading |
| `--verbose` | Show all video status |
| `--re-authenticate` | Force fresh OAuth authentication |

### Cutter

| Option | Description |
|--------|-------------|
| `input` | Input video file (required) |
| `--config PATH` | Path to config file |
| `--path PATH` | Destination path (e.g., Section-F/2026-04-11) |
| `--dry-run` | Preview without cutting |
| `--overwrite` | Overwrite existing files |

## Directory Structure

Recordings can use any directory structure. The date is extracted from:
1. Path segments matching `YYYY-MM-DD`
2. Filenames matching `YYYY-MM-DD.mp4` (when no date in path)

```
Recordings/
├── 2025-05-11/                    # Flat structure
│   ├── Subject 1.mp4
│   └── Subject 2.mp4
├── Section-F/
│   ├── 2026-04-04/
│   │   ├── 1. Sharh Jami 1.mp4
│   │   └── 2. Sharh Jami 2.mp4
│   └── 2026-04-05/
│       └── ...
└── Section-H/
    └── ...
```

For arbitrary recordings (all in same folder):
```
/path/to/config.json
2026-04-01.mp4
2026-04-02.mp4
2026-04-03.mp4
```

## Video Naming

Files should follow: `{number}. {prefix} {part}.mp4`

Example: `1. Sharh Jami 1.mp4` → `Sharh Jami 1: 2026-04-04`

For arbitrary recordings (filename = date): `2026-04-01.mp4` → `Title Prefix: 2026-04-01`

## Playlist Ordering

Videos are ordered based on `yt_playlist_sort`:

- **asc** (default): Part number (ascending), then date (ascending)
- **desc**: Date only (descending)

The script automatically reorders playlists to maintain correct order.
