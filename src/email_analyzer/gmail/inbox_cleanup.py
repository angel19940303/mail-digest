"""Clear remaining Gmail inbox messages after the daily report window."""

from __future__ import annotations

import logging

from email_analyzer.config import AppConfig
from email_analyzer.gmail.actions import apply_post_save_actions
from email_analyzer.gmail.auth import build_gmail_service
from email_analyzer.gmail.fetch import _parse_message_list_item, list_message_ids
from email_analyzer.storage.emails import index_archived_message_ids, save_message

logger = logging.getLogger(__name__)


def cleanup_inbox(config: AppConfig, *, interactive: bool = True) -> int:
    """Archive, mark read, and trash inbox messages outside the report fetch path."""
    if not config.gmail.inbox_cleanup_enabled:
        return 0
    if not config.gmail.mark_read_after_save and not config.gmail.trash_after_save:
        return 0

    service = build_gmail_service(config, interactive=interactive)
    archived = index_archived_message_ids(config)
    items = list_message_ids(service, config.gmail.inbox_cleanup_query)
    if not items:
        return 0

    cleaned = 0
    for item in items:
        message_id = item["id"]
        if message_id in archived:
            apply_post_save_actions(
                service,
                message_id,
                mark_read=config.gmail.mark_read_after_save,
                trash=config.gmail.trash_after_save,
            )
            cleaned += 1
            continue

        detail = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        msg = _parse_message_list_item(item, detail)
        archive_date = msg.internal_datetime.date()
        save_message(config, archive_date, msg, interactive=interactive)
        archived.add(message_id)
        cleaned += 1

    logger.info("Inbox cleanup processed %d message(s)", cleaned)
    return cleaned
