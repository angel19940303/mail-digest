"""Trash inbox messages older than a configured age."""

from __future__ import annotations

import logging

from email_analyzer.config import AppConfig
from email_analyzer.gmail.actions import trash_message
from email_analyzer.gmail.auth import build_gmail_service
from email_analyzer.gmail.fetch import _parse_message_list_item, list_message_ids
from email_analyzer.storage.emails import index_archived_message_ids, save_message

logger = logging.getLogger(__name__)


def _trash_query(config: AppConfig) -> str:
    days = config.gmail.trash_older_than_days
    return f"in:inbox older_than:{days}d"


def cleanup_inbox(config: AppConfig, *, interactive: bool = True) -> int:
    """Archive unread old inbox mail, then move messages older than N days to Trash."""
    days = config.gmail.trash_older_than_days
    if not config.gmail.inbox_cleanup_enabled or days <= 0:
        return 0

    service = build_gmail_service(config, interactive=interactive)
    archived = index_archived_message_ids(config)
    items = list_message_ids(service, _trash_query(config))
    if not items:
        return 0

    trashed = 0
    for item in items:
        message_id = item["id"]
        if message_id not in archived:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            msg = _parse_message_list_item(item, detail)
            save_message(config, msg.internal_datetime.date(), msg, interactive=interactive)
            archived.add(message_id)

        trash_message(service, message_id)
        trashed += 1

    logger.info("Moved %d inbox message(s) older than %d day(s) to trash", trashed, days)
    return trashed
