import json
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from email_analyzer.config import AppConfig, GmailConfig, GMAIL_MODIFY_SCOPE
from email_analyzer.gmail.auth import (
    CHROME_BROWSER_NAME,
    _register_chrome_browser,
    _scopes_satisfied,
    authenticate,
    load_credentials,
)


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


def _write_credentials(config: AppConfig) -> None:
    config.credentials_path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "id",
                    "client_secret": "secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )


def test_authenticate_non_interactive_raises_without_token(tmp_path):
    config = _config(tmp_path)
    _write_credentials(config)

    with pytest.raises(RuntimeError, match="without --non-interactive"):
        authenticate(config, interactive=False)


@patch("email_analyzer.gmail.auth._wait_for_user_ready")
@patch("email_analyzer.gmail.auth._register_chrome_browser", return_value=CHROME_BROWSER_NAME)
@patch("email_analyzer.gmail.auth.InstalledAppFlow.from_client_secrets_file")
def test_authenticate_prompts_and_opens_browser_login(
    mock_flow_factory,
    mock_register_chrome,
    mock_wait,
    tmp_path,
):
    config = _config(tmp_path)
    _write_credentials(config)

    flow = MagicMock()
    creds = MagicMock()
    creds.valid = True
    creds.to_json.return_value = '{"token": "new"}'
    flow.run_local_server.return_value = creds
    mock_flow_factory.return_value = flow

    result = authenticate(config, interactive=True)

    assert result is creds
    mock_wait.assert_called_once()
    mock_register_chrome.assert_called_once()
    flow.run_local_server.assert_called_once_with(
        port=0,
        open_browser=True,
        browser=CHROME_BROWSER_NAME,
    )
    assert config.token_path.exists()


@patch("email_analyzer.gmail.auth.webbrowser.register")
def test_register_chrome_browser_registers_when_chrome_exists(mock_register, tmp_path, monkeypatch):
    chrome_path = tmp_path / "chrome.exe"
    chrome_path.write_bytes(b"chrome")

    monkeypatch.setattr("email_analyzer.gmail.auth._find_chrome_path", lambda: chrome_path)

    browser_name = _register_chrome_browser()

    assert browser_name == CHROME_BROWSER_NAME
    mock_register.assert_called_once()
