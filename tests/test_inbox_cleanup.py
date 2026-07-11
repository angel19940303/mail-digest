from datetime import date
from unittest.mock import MagicMock, patch

from email_analyzer.config import AppConfig, GmailConfig, PathsConfig, ScheduleConfig
from email_analyzer.gmail.inbox_cleanup import cleanup_inbox
from email_analyzer.storage.emails import index_archived_message_ids


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=GmailConfig(
            inbox_cleanup_enabled=True,
            trash_older_than_days=7,
            mark_read_after_save=True,
        ),
        paths=PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
    )


@patch("email_analyzer.gmail.inbox_cleanup.save_message")
@patch("email_analyzer.gmail.inbox_cleanup.trash_message")
@patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service")
@patch("email_analyzer.gmail.inbox_cleanup.list_message_ids")
def test_cleanup_inbox_archives_then_trashes_unarchived_old_mail(
    mock_list,
    mock_build_service,
    mock_trash,
    mock_save,
    tmp_path,
):
    config = _config(tmp_path)
    mock_list.return_value = [{"id": "old1"}]
    service = MagicMock()
    mock_build_service.return_value = service
    service.users().messages().get().execute.return_value = {
        "id": "old1",
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
    mock_list.assert_called_once_with(service, "in:inbox older_than:7d")
    mock_save.assert_called_once()
    saved_date = mock_save.call_args.args[1]
    assert saved_date == date(2024, 6, 19)
    mock_trash.assert_called_once_with(service, "old1")


@patch("email_analyzer.gmail.inbox_cleanup.save_message")
@patch("email_analyzer.gmail.inbox_cleanup.trash_message")
@patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service")
@patch("email_analyzer.gmail.inbox_cleanup.list_message_ids")
def test_cleanup_inbox_only_trashes_already_archived_old_mail(
    mock_list,
    mock_build_service,
    mock_trash,
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
    mock_trash.assert_called_once()


def test_cleanup_inbox_disabled(tmp_path):
    config = _config(tmp_path)
    config.gmail.inbox_cleanup_enabled = False

    with patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service") as mock_build:
        assert cleanup_inbox(config, interactive=False) == 0
        mock_build.assert_not_called()


def test_cleanup_inbox_skipped_when_trash_days_zero(tmp_path):
    config = _config(tmp_path)
    config.gmail.trash_older_than_days = 0

    with patch("email_analyzer.gmail.inbox_cleanup.build_gmail_service") as mock_build:
        assert cleanup_inbox(config, interactive=False) == 0
        mock_build.assert_not_called()


def test_index_archived_message_ids(tmp_path):
    config = _config(tmp_path)
    archive_dir = tmp_path / "emails" / "2026" / "2026-06" / "2026-06-10"
    archive_dir.mkdir(parents=True)
    (archive_dir / "abc.meta.json").write_text(
        '{"message_id": "abc"}',
        encoding="utf-8",
    )

    assert index_archived_message_ids(config) == {"abc"}
