from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ModuleNotFoundError:
    Request = None
    Credentials = None
    InstalledAppFlow = None
    build = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SECRETS_DIR = PROJECT_ROOT / "secrets"
CLIENT_SECRET_PATH = SECRETS_DIR / "youtube_oauth_client_secret.json"
TOKEN_PATH = SECRETS_DIR / "youtube_oauth_token.json"

READONLY_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

UPLOAD_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
]

# Keep the broad YouTube scope in the default token as well. Scheduled uploads use
# youtube.upload, analytics uses read-only scopes, and operational cleanup can need
# videos.delete; requesting a consistent superset avoids refresh failures when an
# older token was authorized with a different YouTube scope set.
MANAGE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]

DEFAULT_SCOPES = READONLY_SCOPES + UPLOAD_SCOPES + MANAGE_SCOPES


def ensure_secrets_dir() -> Path:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SECRETS_DIR, 0o700)
    except OSError:
        pass
    return SECRETS_DIR


def credentials_paths() -> dict[str, str]:
    return {
        "secrets_dir": str(SECRETS_DIR),
        "client_secret": str(CLIENT_SECRET_PATH),
        "token": str(TOKEN_PATH),
    }


def _require_google_api_dependencies() -> None:
    if (
        Request is None
        or Credentials is None
        or InstalledAppFlow is None
        or build is None
    ):
        raise RuntimeError(
            "Google API dependencies are not installed. Install project requirements "
            "or run: python -m pip install google-api-python-client "
            "google-auth google-auth-oauthlib google-auth-httplib2"
        )


def load_credentials(scopes: Iterable[str] | None = None) -> Credentials | None:
    _require_google_api_dependencies()
    scopes = list(scopes or DEFAULT_SCOPES)
    if not TOKEN_PATH.exists():
        return None
    return Credentials.from_authorized_user_file(str(TOKEN_PATH), scopes=scopes)


def save_credentials(creds: Credentials) -> None:
    _require_google_api_dependencies()
    ensure_secrets_dir()
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def get_credentials(scopes: Iterable[str] | None = None, interactive: bool = False) -> Credentials:
    """Load/refresh OAuth credentials. If interactive=True, run the first-time OAuth flow."""
    _require_google_api_dependencies()
    scopes = list(scopes or DEFAULT_SCOPES)
    ensure_secrets_dir()
    creds = load_credentials(scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
        return creds

    if not interactive:
        raise RuntimeError(
            "YouTube OAuth token is not available or refreshable for the requested scopes. "
            f"Place OAuth client JSON at {CLIENT_SECRET_PATH}, delete any old token, "
            "and run scripts/setup_youtube_oauth.py."
        )

    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"Missing OAuth client secret JSON: {CLIENT_SECRET_PATH}\n"
            "Create a Google Cloud OAuth Desktop client and save the downloaded JSON there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), scopes=scopes)
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        authorization_prompt_message=(
            "Open this URL in the logged-in YouTube channel browser if it does not open automatically:\n{url}\n"
        ),
        success_message="YouTube OAuth authorization complete. You can close this browser tab.",
        open_browser=False,
        prompt="consent",
    )
    save_credentials(creds)
    return creds


def youtube_data_service(credentials: Credentials | None = None):
    _require_google_api_dependencies()
    return build("youtube", "v3", credentials=credentials or get_credentials(), cache_discovery=False)


def youtube_analytics_service(credentials: Credentials | None = None):
    _require_google_api_dependencies()
    return build("youtubeAnalytics", "v2", credentials=credentials or get_credentials(), cache_discovery=False)


def token_status() -> dict:
    client_exists = CLIENT_SECRET_PATH.exists()
    token_exists = TOKEN_PATH.exists()
    status = {
        **credentials_paths(),
        "client_secret_exists": client_exists,
        "token_exists": token_exists,
        "token_valid": False,
        "token_expired": None,
        "has_refresh_token": False,
        "scopes": DEFAULT_SCOPES,
    }
    if token_exists:
        try:
            creds = load_credentials(DEFAULT_SCOPES)
            status.update(
                {
                    "token_valid": bool(creds and creds.valid),
                    "token_expired": bool(creds and creds.expired),
                    "has_refresh_token": bool(creds and creds.refresh_token),
                }
            )
        except Exception as exc:  # noqa: BLE001 - status should not leak token content
            status["token_error"] = f"{type(exc).__name__}: {exc}"
    return status


def print_token_status() -> None:
    print(json.dumps(token_status(), ensure_ascii=False, indent=2))
