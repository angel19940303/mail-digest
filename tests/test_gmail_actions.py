from unittest.mock import MagicMock

from email_analyzer.gmail.actions import apply_post_save_actions, mark_message_read, trash_message


def test_mark_message_read():
    service = MagicMock()
    mark_message_read(service, "abc123")
    service.users().messages().modify.assert_called_once_with(
        userId="me",
        id="abc123",
        body={"removeLabelIds": ["UNREAD"]},
    )


def test_trash_message():
    service = MagicMock()
    trash_message(service, "abc123")
    service.users().messages().trash.assert_called_once_with(userId="me", id="abc123")


def test_apply_post_save_actions_both():
    service = MagicMock()
    apply_post_save_actions(service, "abc123", mark_read=True, trash=True)
    service.users().messages().modify.assert_called_once()
    service.users().messages().trash.assert_called_once()


def test_apply_post_save_actions_mark_only():
    service = MagicMock()
    apply_post_save_actions(service, "abc123", mark_read=True, trash=False)
    service.users().messages().modify.assert_called_once()
    service.users().messages().trash.assert_not_called()
