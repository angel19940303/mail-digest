import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from email_analyzer.config import AppConfig, GmailConfig, PathsConfig, ScheduleConfig
from email_analyzer.gmail.fetch import EmailMessage, fetch_messages_in_window


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=GmailConfig(broad_query="in:inbox newer_than:2d"),
        paths=PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
    )


def _write_archive(tmp_path, message_id: str, *, internal_date_ms: int) -> EmailMessage:
    archive_dir = tmp_path / "emails" / "2026" / "2026-06" / "2026-06-19"
    archive_dir.mkdir(parents=True)
    msg = EmailMessage(
        message_id=message_id,
        thread_id="t1",
        internal_date_ms=internal_date_ms,
        from_addr="Sender <sender@example.com>",
        from_email="sender@example.com",
        subject="Cached mail",
        date_header="",
        snippet="snippet",
        labels=["INBOX"],
        body_text="cached body",
        category="other",
    )
    (archive_dir / f"{message_id}.meta.json").write_text(
        json.dumps(
            {
                "message_id": message_id,
                "thread_id": "t1",
                "internal_date_ms": msg.internal_date_ms,
                "from_addr": msg.from_addr,
                "from_email": msg.from_email,
                "subject": msg.subject,
                "date_header": "",
                "snippet": msg.snippet,
                "labels": msg.labels,
                "body_text": msg.body_text,
                "category": "other",
            }
        ),
        encoding="utf-8",
    )
    return msg


@patch("email_analyzer.gmail.fetch.build_gmail_service")
@patch("email_analyzer.gmail.fetch.list_message_ids")
def test_fetch_uses_local_archive_when_message_is_read(mock_list, mock_build_service, tmp_path):
    config = _config(tmp_path)
    window_start = datetime(2026, 6, 18, 18, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 6, 19, 18, 0, tzinfo=timezone.utc)
    internal_ms = int((window_start.timestamp() + 3600) * 1000)
    cached = _write_archive(tmp_path, "cached1", internal_date_ms=internal_ms)

    mock_list.return_value = [{"id": "cached1"}]
    service = MagicMock()
    mock_build_service.return_value = service
    get_mock = service.users.return_value.messages.return_value.get
    get_mock.return_value.execute.return_value = {
        "internalDate": str(cached.internal_date_ms),
        "labelIds": ["INBOX"],
    }

    messages = fetch_messages_in_window(
        config,
        window_start,
        window_end,
        interactive=False,
    )

    assert len(messages) == 1
    assert messages[0].message_id == "cached1"
    assert messages[0].body_text == "cached body"
    get_mock = service.users.return_value.messages.return_value.get
    formats = [call.kwargs.get("format") for call in get_mock.call_args_list]
    assert formats == ["metadata"]


@patch("email_analyzer.gmail.fetch.build_gmail_service")
@patch("email_analyzer.gmail.fetch.list_message_ids")
def test_fetch_downloads_unread_message_even_if_archived(mock_list, mock_build_service, tmp_path):
    config = _config(tmp_path)
    window_start = datetime(2026, 6, 18, 18, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 6, 19, 18, 0, tzinfo=timezone.utc)
    internal_ms = int((window_start.timestamp() + 3600) * 1000)
    cached = _write_archive(tmp_path, "cached1", internal_date_ms=internal_ms)

    mock_list.return_value = [{"id": "cached1"}]
    service = MagicMock()
    mock_build_service.return_value = service
    get_mock = service.users.return_value.messages.return_value.get
    metadata = {
        "internalDate": str(cached.internal_date_ms),
        "labelIds": ["INBOX", "UNREAD"],
    }
    full_detail = {
        "id": "cached1",
        "threadId": "t1",
        "internalDate": str(cached.internal_date_ms),
        "snippet": "fresh",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "Subject", "value": "Cached mail"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "ZnJlc2g="},
        },
    }
    get_mock.return_value.execute.side_effect = [metadata, full_detail]

    messages = fetch_messages_in_window(
        config,
        window_start,
        window_end,
        interactive=False,
    )

    assert len(messages) == 1
    assert messages[0].body_text == "fresh"
    get_mock = service.users.return_value.messages.return_value.get
    formats = [call.kwargs.get("format") for call in get_mock.call_args_list]
    assert formats == ["metadata", "full"]
