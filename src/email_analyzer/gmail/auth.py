"""Gmail OAuth2 authentication."""

from __future__ import annotations

import json
import logging

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from email_analyzer.config import AppConfig, GMAIL_MODIFY_SCOPE

logger = logging.getLogger(__name__)

SCOPES = [GMAIL_MODIFY_SCOPE]

REAUTH_HINT = (
    "Delete token.json and run: python -m email_analyzer auth"
)


def _scopes_satisfied(granted: list[str] | None, required: list[str]) -> bool:
    return set(required).issubset(set(granted or []))


def _clear_token(config: AppConfig) -> None:
    config.token_path.unlink(missing_ok=True)


def _refresh_error_needs_reauth(exc: RefreshError) -> bool:
    msg = str(exc).lower()
    return any(
        keyword in msg
        for keyword in ("invalid_scope", "invalid_grant", "expired", "revoked")
    )


def _token_granted_scopes(token_path) -> list[str] | None:
    data = json.loads(token_path.read_text(encoding="utf-8"))
    scopes = data.get("scopes")
    if scopes:
        return [str(s) for s in scopes]
    scope = data.get("scope")
    if scope:
        return str(scope).split()
    return None


def load_credentials(config: AppConfig) -> Credentials | None:
    token_path = config.token_path
    if not token_path.exists():
        return None
    granted = _token_granted_scopes(token_path)
    if granted is not None and not _scopes_satisfied(granted, config.gmail.scopes):
        _clear_token(config)
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), config.gmail.scopes)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(config, creds)
        except RefreshError as exc:
            if _refresh_error_needs_reauth(exc):
                logger.warning("Gmail token refresh failed (%s); clearing token", exc)
                _clear_token(config)
                return None
            raise
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
        raise RuntimeError(
            "Gmail token is missing, expired, or has insufficient scopes for this config. "
            f"{REAUTH_HINT}"
        )
    save_credentials(config, creds)
    return creds


def build_gmail_service(config: AppConfig, *, interactive: bool = True):
    creds = authenticate(config, interactive=interactive)
    return build("gmail", "v1", credentials=creds)
