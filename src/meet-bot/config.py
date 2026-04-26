import argparse
from pathlib import Path
from dataclasses import dataclass


DEFAULT_POLL_INTERVAL = 30
DEFAULT_TOKEN_PATH = Path(__file__).parent / "token.json"
DEFAULT_CLIENT_SECRET_PATH = Path(__file__).parent / "client_secret.json"
DEFAULT_SESSION_PATH = Path(__file__).parent / "chrome_session.json"


@dataclass
class Config:
    meet_link: str
    message: str
    poll_interval: int = DEFAULT_POLL_INTERVAL
    token_path: Path = DEFAULT_TOKEN_PATH
    client_secret_path: Path = DEFAULT_CLIENT_SECRET_PATH
    headless: bool = True
    session_path: Path = DEFAULT_SESSION_PATH
    strict_media: bool = True
    debug: bool = False
    new_session: bool = False


def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="Google Meet Bot - Join meeting and welcome participants"
    )
    parser.add_argument(
        "--meet-link",
        type=str,
        required=True,
        help="Google Meet link (e.g., https://meet.google.com/abc-mnop-xyz)",
    )
    parser.add_argument(
        "--message",
        type=str,
        required=True,
        help="Message to send when someone joins",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Interval in seconds to check for new participants (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--token-path",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Path to OAuth token file (default: token.json)",
    )
    parser.add_argument(
        "--client-secret",
        type=Path,
        default=DEFAULT_CLIENT_SECRET_PATH,
        help="Path to OAuth client secret file (default: client_secret.json)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (not headless)",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help=f"Path to browser session state JSON (default: {DEFAULT_SESSION_PATH})",
    )
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Force re-create browser session (login again)",
    )
    parser.add_argument(
        "--no-strict-media",
        action="store_true",
        help="Don't require camera/mic to be turned off before joining (default: strict)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and screenshots",
    )

    args = parser.parse_args()

    return Config(
        meet_link=args.meet_link,
        message=args.message,
        poll_interval=args.poll_interval,
        token_path=args.token_path,
        client_secret_path=args.client_secret,
        headless=not args.no_headless,
        session_path=Path(args.session) if args.session else DEFAULT_SESSION_PATH,
        strict_media=not args.no_strict_media,
        debug=args.debug,
        new_session=args.new_session,
    )


def extract_meeting_code(meet_link: str) -> str:
    """Extract meeting code from Google Meet URL."""
    if "meet.google.com/" in meet_link:
        code = meet_link.split("meet.google.com/")[-1].split("?")[0]
        return code
    raise ValueError(f"Invalid Google Meet link: {meet_link}")