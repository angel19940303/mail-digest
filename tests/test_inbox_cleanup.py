from datetime import date
from unittest.mock import MagicMock, patch

from email_analyzer.config import AppConfig, GmailConfig, PathsConfig, ScheduleConfig
from email_analyzer.gmail.fetch import EmailMessage
from email_analyzer.gmail.inbox_cleanup import cleanup_inbox
from email_analyzer.storage.emails import index_archived_message_ids


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=GmailConfig(
            inbox_cleanup_query="in:inbox",
            inbox_cleanup_enabled=True,
            mark_read_after_save=True,
            trash_after_save=True,
        ),
        paths=PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
    )


def _msg(message_id: str) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        thread_id="t1",
        internal_date_ms=1_718_800_000_000,
        from_addr="Sender <sender@example.com>",
        from_email="sender@example.com",
        subject="Old inbox mail",
        date_header="",
        snippet="",
        body_text="body",
    )


def test_index_archived_message_ids(tmp_path):
    config = _config(tmp_path)
    archive_dir = (
        tmp_path
        / "emails"
        / "2026"
        / "2026-06"
        / "2026-06-10"
    )
    archive_dir.mkdir(parents=True)
    (archive_dir / "abc.meta.json").write_text(
        '{"message_id": "abc"}',
        encoding="utf-8",
    )

    assert index_archived_message_ids(config) == {"abc"}


@patch("email_analyzer.gmail.inbox_cleanup.save_message")
@patch("email_analyzer.gmail.inbox_cleanup.apply_post_save_actions")
@patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service")
@patch("email_analyzer.gmail.inbox_cleanup.list_message_ids")
def test_cleanup_inbox_archives_new_messages(
    mock_list,
    mock_build_service,
    mock_apply,
    mock_save,
    tmp_path,
):
    config = _config(tmp_path)
    mock_list.return_value = [{"id": "new1"}]
    service = MagicMock()
    mock_build_service.return_value = service
    service.users().messages().get().execute.return_value = {
        "id": "new1",
        "threadId": "t1",
        "internalDate": "1718800000000",
        "snippet": "",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "Subject", "value": "Old inbox mail"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "Ym9keQ=="},
        },
    }

    cleaned = cleanup_inbox(config, interactive=False)

    assert cleaned == 1
    mock_save.assert_called_once()
    saved_date = mock_save.call_args.args[1]
    assert saved_date == date(2024, 6, 19)
    mock_apply.assert_not_called()


@patch("email_analyzer.gmail.inbox_cleanup.save_message")
@patch("email_analyzer.gmail.inbox_cleanup.apply_post_save_actions")
@patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service")
@patch("email_analyzer.gmail.inbox_cleanup.list_message_ids")
def test_cleanup_inbox_only_post_save_for_archived_messages(
    mock_list,
    mock_build_service,
    mock_apply,
    mock_save,
    tmp_path,
):
    config = _config(tmp_path)
    archive_dir = tmp_path / "emails" / "2026" / "2026-06" / "2026-06-10"
    archive_dir.mkdir(parents=True)
    (archive_dir / "old1.meta.json").write_text(
        '{"message_id": "old1"}',
        encoding="utf-8",
    )

    mock_list.return_value = [{"id": "old1"}]
    mock_build_service.return_value = MagicMock()

    cleaned = cleanup_inbox(config, interactive=False)

    assert cleaned == 1
    mock_save.assert_not_called()
    mock_apply.assert_called_once_with(
        mock_build_service.return_value,
        "old1",
        mark_read=True,
        trash=True,
    )


def test_cleanup_inbox_disabled(tmp_path):
    config = _config(tmp_path)
    config.gmail.inbox_cleanup_enabled = False

    with patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service") as mock_build:
        assert cleanup_inbox(config, interactive=False) == 0
        mock_build.assert_not_called()
