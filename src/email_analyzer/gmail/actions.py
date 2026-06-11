"""Gmail inbox actions after local archive."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def mark_message_read(service, message_id: str) -> None:
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
    logger.debug("Marked message %s as read", message_id)


def trash_message(service, message_id: str) -> None:
    service.users().messages().trash(userId="me", id=message_id).execute()
    logger.debug("Moved message %s to Gmail trash", message_id)


def apply_post_save_actions(
    service,
    message_id: str,
    *,
    mark_read: bool,
    trash: bool,
) -> None:
    if mark_read:
        mark_message_read(service, message_id)
    if trash:
        trash_message(service, message_id)
