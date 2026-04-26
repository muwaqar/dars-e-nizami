# Google Meet Bot

Joins a Google Meet meeting and sends a configurable message when new participants join.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a Google OAuth client secret:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project or use existing
   - Enable the "Google Meet API"
   - Create OAuth credentials (Desktop app)
   - Download the JSON and save as `client_secret.json` in this directory

3. Create browser session:
```bash
python main.py --meet-link "https://meet.google.com/xxx-xxxx-xxx" --message "Hello" --new-session
```
This will open a browser window for you to sign in to your Google account.

## Usage

```bash
python main.py --meet-link "https://meet.google.com/xxx-xxxx-xxx" --message "Welcome!"
```

### Options

- `--meet-link` - Google Meet URL (required)
- `--message` - Message to send when someone joins (required)
- `--poll-interval` - Seconds between participant checks (default: 10)
- `--no-headless` - Show browser window
- `--debug` - Enable verbose logging
- `--new-session` - Force re-login
- `--session PATH` - Use specific browser session file
- `--no-strict-media` - Don't require camera/mic to be off

### Example

```bash
python main.py \
  --meet-link "https://meet.google.com/abc-defg-hij" \
  --message "Assalam o Alaikum! Welcome to Dars-e-Nizami." \
  --poll-interval 5 \
  --no-headless
```

## How It Works

1. Authenticates with Google Meet API using OAuth
2. Joins the meeting via browser automation (Playwright)
3. Sends initial message immediately after joining
4. Polls the Meet API every N seconds to detect new participant sessions
5. Sends the message whenever a new session is detected (including re-joins from same user on different devices)
6. Exits gracefully on Ctrl+C