# Google Meet Bot

Automated bot that joins a Google Meet and sends welcome messages when participants join.

## Features

- Join Google Meet automatically (mic/camera off by default)
- Detect new participants via Google Meet REST API
- Send welcome messages to meeting chat
- Configurable polling interval
- Headless mode support

## Prerequisites

1. **Python 3.8+**
2. **Chrome browser** (installed)
3. **Google Cloud account** with Meet API enabled

## Setup

### 1. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable **Google Meet API**
4. Go to **APIs & Services > Credentials**
5. Create **OAuth client ID** (Desktop application)
6. Download the JSON and save as `client_secret.json` in this directory

### 2. Install Dependencies

```bash
cd src/meet-bot
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
python -m main \
    --meet-link "https://meet.google.com/abc-mnop-xyz" \
    --message "Welcome to the class!"
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--meet-link` | Google Meet URL (required) | - |
| `--message` | Message to send (required) | - |
| `--poll-interval` | Seconds between participant checks | 30 |
| `--client-secret` | Path to OAuth client secret | `./client_secret.json` |
| `--token-path` | Path to OAuth token | `./token.json` |
| `--no-headless` | Run browser in visible mode | false (headless) |

## First Run

On first run, you'll be prompted to authenticate with Google:

1. Browser window opens
2. Sign in with your Google account
3. Grant permissions (Meet API access)
4. Token is saved for future runs

## Notes

- The bot uses Google Meet REST API to detect participants - this requires authentication
- Guest mode cannot use the Meet API for participant detection
- Chat messages are sent via browser automation
- The bot will continue running until you interrupt (Ctrl+C) or leave the meeting

## Troubleshooting

**"Client secret file not found"**
- Ensure `client_secret.json` is in the meet-bot directory

**"Failed to join meeting"**
- Check that the meeting link is correct
- Try with `--no-headless` to see what's happening

**"Failed to send chat message"**
- The chat panel may need time to load
- Ensure you're actually in the meeting (not in waiting room)