"""Gmail OAuth2 authentication."""

from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from email_analyzer.config import AppConfig, GMAIL_MODIFY_SCOPE

SCOPES = [GMAIL_MODIFY_SCOPE]


def load_credentials(config: AppConfig) -> Credentials | None:
    token_path = config.token_path
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), config.gmail.scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(config, creds)
    return creds


def save_credentials(config: AppConfig, creds: Credentials) -> None:
    config.token_path.write_text(creds.to_json(), encoding="utf-8")


def authenticate(config: AppConfig, *, interactive: bool = True) -> Credentials:
    creds = load_credentials(config)
    if creds and creds.valid:
        return creds

    creds_path = config.credentials_path
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Gmail credentials not found at {creds_path}. "
            "Download OAuth client JSON from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), config.gmail.scopes)
    if interactive:
        creds = flow.run_local_server(port=0)
    else:
        raise RuntimeError("Gmail token expired and non-interactive auth is not available.")
    save_credentials(config, creds)
    return creds


def build_gmail_service(config: AppConfig, *, interactive: bool = True):
    creds = authenticate(config, interactive=interactive)
    return build("gmail", "v1", credentials=creds)
