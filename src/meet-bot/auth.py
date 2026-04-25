import os
import logging
from pathlib import Path
from typing import Optional

from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/meetings.space.created",
]


def get_credentials(
    token_path: Path,
    client_secret_path: Path,
    force_reauth: bool = False,
) -> Credentials:
    """
    Get OAuth credentials, handling token storage and refresh.

    Args:
        token_path: Path to store/load the OAuth token
        client_secret_path: Path to the OAuth client secret JSON
        force_reauth: If True, force re-authentication even if token exists

    Returns:
        Valid OAuth credentials
    """
    if not client_secret_path.exists():
        raise FileNotFoundError(
            f"Client secret file not found: {client_secret_path}\n"
            "Please download OAuth credentials from Google Cloud Console:\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create a project or select existing\n"
            "3. Enable Google Meet API\n"
            "4. Go to APIs & Services > Credentials\n"
            "5. Create OAuth client ID (Desktop app)\n"
            "6. Download the client secret JSON"
        )

    credentials: Optional[OAuth2Credentials] = None

    if not force_reauth and token_path.exists():
        try:
            token_data = _load_token_json(token_path)
            credentials = OAuth2Credentials.from_authorized_user_info(
                token_data,
                scopes=SCOPES,
            )
        except Exception as e:
            logger.warning(f"Existing token invalid or expired, re-authenticating...")
            credentials = None

    if credentials is None or force_reauth:
        logger.info("Please authenticate in the browser window that opens...")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            scopes=SCOPES,
        )
        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )
        _save_token_json(token_path, credentials)
        logger.info("Authentication successful! Token saved.")

    if credentials and getattr(credentials, 'expired', None):
        logger.info("Token expired, refreshing...")
        try:
            from google.auth.transport.requests import Request
            request = Request()
            credentials.refresh(request)
            _save_token_json(token_path, credentials)
            logger.info("Token refreshed.")
        except Exception as e:
            logger.warning(f"Refresh failed: {e}, re-authenticating...")
            credentials = None

    if credentials is None:
        logger.info("Please authenticate in the browser window that opens...")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            scopes=SCOPES,
        )
        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )
        _save_token_json(token_path, credentials)
        logger.info("Authentication successful! Token saved.")

    return credentials


def _load_token_json(token_path: Path) -> dict:
    """Load token from JSON file."""
    import json
    with open(token_path, "r") as f:
        return json.load(f)


def _save_token_json(token_path: Path, credentials: Credentials) -> None:
    """Save token to JSON file."""
    import json
    token_info = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
    }
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        json.dump(token_info, f, indent=2)