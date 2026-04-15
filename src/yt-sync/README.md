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

1. Copy `sample-config.json` to `config.json` and edit with your playlists:

```json
{
  "default_privacy": "unlisted",
  "playlists": {
    "Subject Name": "PLAYLIST_ID"
  }
}
```

2. Place your `client_secret.json` (from Google Cloud Console) in this directory.

3. On first run, authenticate with YouTube (opens browser).

## Usage

```bash
# Run from src/yt-sync/ directory
cd src/yt-sync/

# Preview mode
python3 syncer.py --dry-run

# Sync all recordings
python3 syncer.py

# Sync specific path
python3 syncer.py --path Section-F
python3 syncer.py --path Section-F/2026-04-11

# Verbose output
python3 syncer.py --verbose

# Re-authenticate (force new OAuth flow)
python3 syncer.py --re-authenticate
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to config file (default: config.json) |
| `--credentials PATH` | Path to client_secret.json (default: ./client_secret.json) |
| `--path GLOB` | Filter recordings by path (e.g., 'Section-F', 'Section-F/2026-04-11') |
| `--dry-run` | Preview without uploading |
| `--verbose` | Show all video status |
| `--re-authenticate` | Force fresh OAuth authentication |

## Directory Structure

Recordings can use any directory structure. The date is extracted from path segments matching `YYYY-MM-DD`.

```
Recordings/
├── 2025-05-11/                    # Flat structure
│   ├── Subject 1.mp4
│   └── Subject 2.mp4
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