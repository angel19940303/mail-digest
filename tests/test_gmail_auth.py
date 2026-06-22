import json
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from email_analyzer.config import AppConfig, GmailConfig, GMAIL_MODIFY_SCOPE
from email_analyzer.gmail.auth import _scopes_satisfied, load_credentials


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=__import__("email_analyzer.config", fromlist=["ScheduleConfig"]).ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=GmailConfig(scopes=[GMAIL_MODIFY_SCOPE], token_file="token.json"),
        paths=__import__("email_analyzer.config", fromlist=["PathsConfig"]).PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
    )


def test_scopes_satisfied():
    readonly = ["https://www.googleapis.com/auth/gmail.readonly"]
    modify = [GMAIL_MODIFY_SCOPE]
    assert not _scopes_satisfied(readonly, modify)
    assert _scopes_satisfied(modify, modify)


def test_load_credentials_clears_token_on_scope_mismatch(tmp_path):
    config = _config(tmp_path)
    token = {
        "token": "x",
        "refresh_token": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }
    config.token_path.write_text(json.dumps(token), encoding="utf-8")

    assert load_credentials(config) is None
    assert not config.token_path.exists()


def test_load_credentials_clears_token_on_invalid_scope_refresh(tmp_path):
    config = _config(tmp_path)
    token = {
        "token": "x",
        "refresh_token": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
        "scopes": [GMAIL_MODIFY_SCOPE],
        "expiry": "2000-01-01T00:00:00Z",
    }
    config.token_path.write_text(json.dumps(token), encoding="utf-8")

    creds = MagicMock()
    creds.scopes = [GMAIL_MODIFY_SCOPE]
    creds.expired = True
    creds.refresh_token = "y"
    creds.refresh.side_effect = RefreshError("invalid_scope: Bad Request")

    with patch("email_analyzer.gmail.auth.Credentials.from_authorized_user_file", return_value=creds):
        assert load_credentials(config) is None
    assert not config.token_path.exists()


def test_load_credentials_clears_token_on_invalid_grant_refresh(tmp_path):
    config = _config(tmp_path)
    token = {
        "token": "x",
        "refresh_token": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
        "scopes": [GMAIL_MODIFY_SCOPE],
        "expiry": "2000-01-01T00:00:00Z",
    }
    config.token_path.write_text(json.dumps(token), encoding="utf-8")

    creds = MagicMock()
    creds.scopes = [GMAIL_MODIFY_SCOPE]
    creds.expired = True
    creds.refresh_token = "y"
    creds.refresh.side_effect = RefreshError(
        "invalid_grant: Token has been expired or revoked.",
        {"error": "invalid_grant", "error_description": "Token has been expired or revoked."},
    )

    with patch("email_analyzer.gmail.auth.Credentials.from_authorized_user_file", return_value=creds):
        assert load_credentials(config) is None
    assert not config.token_path.exists()
