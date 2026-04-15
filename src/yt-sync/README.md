# yt-sync

Sync local recordings to YouTube and organize them into playlists.

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt
```

## Configuration

1. Copy `sample-config.json` to your config location and edit it:

```json
{
  "default_privacy": "unlisted",
  "playlists": {
    "Subject Name": "PLAYLIST_ID"
  }
}
```

2. Place your `client_secret.json` (from Google Cloud Console) in the working directory.

3. The first run will authenticate with YouTube (opens browser).

## Usage

```bash
# Basic usage (from working directory with config.json in parent of Recordings)
python3 -m yt_sync.syncer --dry-run

# Specify config file
python3 -m yt_sync.syncer --config path/to/config.json --dry-run

# Specify credentials
python3 -m yt_sync.syncer --credentials path/to/client_secret.json --dry-run

# Sync specific section/date
python3 -m yt_sync.syncer --section F --date 2026-04-11 --dry-run

# Verbose output
python3 -m yt_sync.syncer --verbose

# Re-authenticate (force new OAuth flow)
python3 -m yt_sync.syncer --re-authenticate
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to config file (default: auto-detected) |
| `--credentials PATH` | Path to client_secret.json (default: ./client_secret.json) |
| `--section F\|H` | Sync specific section |
| `--date YYYY-MM-DD` | Sync specific date |
| `--dry-run` | Preview without uploading |
| `--verbose` | Show all video status |
| `--re-authenticate` | Force fresh OAuth authentication |

## Directory Structure

Recordings are expected in this structure:
```
Recordings/
├── Section-F/
│   ├── 2026-04-04/
│   │   ├── 1. Subject 1.mp4
│   │   └── 2. Subject 2.mp4
│   └── 2026-04-05/
│       └── ...
└── Section-H/
    └── ...
```

## Video Naming

Files should follow: `{number}. {Subject} {part}.mp4`

Example: `1. Sharh Jami 1.mp4` → `Sharh Jami 1: 2026-04-04`

## Playlist Ordering

Videos are ordered by:
1. Part number (ascending)
2. Date (ascending)

The script automatically reorders playlists to maintain correct order.
