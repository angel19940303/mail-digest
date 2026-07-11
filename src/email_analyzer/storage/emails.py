"""Persist fetched emails to disk."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from email_analyzer.config import AppConfig
from email_analyzer.gmail.actions import mark_message_read
from email_analyzer.gmail.auth import build_gmail_service
from email_analyzer.gmail.fetch import EmailMessage, download_raw_eml
from email_analyzer.storage.paths import emails_dir

logger = logging.getLogger(__name__)


def _meta_path(dest: Path, message_id: str) -> Path:
    return dest / f"{message_id}.meta.json"


def _eml_path(dest: Path, message_id: str) -> Path:
    return dest / f"{message_id}.eml"


def message_to_meta(msg: EmailMessage) -> dict:
    data = asdict(msg)
    data["internal_datetime"] = msg.internal_datetime.isoformat()
    return data


def _mark_saved_message_read(
    config: AppConfig,
    service,
    message_id: str,
) -> None:
    if config.gmail.mark_read_after_save:
        mark_message_read(service, message_id)


def save_message(
    config: AppConfig,
    report_date: date,
    msg: EmailMessage,
    *,
    interactive: bool = True,
) -> Path:
    dest = emails_dir(config, report_date)
    dest.mkdir(parents=True, exist_ok=True)

    meta_path = _meta_path(dest, msg.message_id)
    eml_path = _eml_path(dest, msg.message_id)
    service = None

    if not eml_path.exists():
        service = build_gmail_service(config, interactive=interactive)
        eml_path.write_bytes(download_raw_eml(service, msg.message_id))

    meta_path.write_text(
        json.dumps(message_to_meta(msg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if config.gmail.mark_read_after_save:
        if service is None:
            service = build_gmail_service(config, interactive=interactive)
        _mark_saved_message_read(config, service, msg.message_id)
    return dest


def save_messages(
    config: AppConfig,
    report_date: date,
    messages: list[EmailMessage],
    *,
    interactive: bool = True,
) -> list[Path]:
    if not messages:
        dest = emails_dir(config, report_date)
        dest.mkdir(parents=True, exist_ok=True)
        return [dest]

    saved: list[Path] = []
    service = None
    dest = emails_dir(config, report_date)
    dest.mkdir(parents=True, exist_ok=True)

    for msg in messages:
        meta_path = _meta_path(dest, msg.message_id)
        eml_path = _eml_path(dest, msg.message_id)

        if not eml_path.exists():
            if service is None:
                service = build_gmail_service(config, interactive=interactive)
            eml_path.write_bytes(download_raw_eml(service, msg.message_id))

        meta_path.write_text(
            json.dumps(message_to_meta(msg), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if config.gmail.mark_read_after_save:
            if service is None:
                service = build_gmail_service(config, interactive=interactive)
            _mark_saved_message_read(config, service, msg.message_id)

        saved.append(dest)
    return saved


def purge_old_archives(config: AppConfig, *, today: date | None = None) -> int:
    """Delete local email archives older than email_retention_days. Returns dirs removed."""
    retention = config.paths.email_retention_days
    if retention <= 0:
        return 0

    cutoff = (today or date.today()) - timedelta(days=retention)
    base = config.resolve(config.paths.emails)
    if not base.exists():
        return 0

    removed = 0
    seen: set[Path] = set()
    for meta_file in base.rglob("*.meta.json"):
        archive_dir = meta_file.parent
        if archive_dir in seen:
            continue
        seen.add(archive_dir)
        try:
            archive_date = date.fromisoformat(archive_dir.name)
        except ValueError:
            continue
        if archive_date >= cutoff:
            continue
        shutil.rmtree(archive_dir)
        removed += 1
        logger.info("Purged old email archive: %s", archive_dir)

    return removed


def index_archived_message_ids(config: AppConfig) -> set[str]:
    """Return Gmail message IDs that already have a local archive."""
    base = config.resolve(config.paths.emails)
    if not base.exists():
        return set()

    ids: set[str] = set()
    for meta_file in base.rglob("*.meta.json"):
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        message_id = data.get("message_id")
        if message_id:
            ids.add(message_id)
    return ids


def _meta_to_message(data: dict) -> EmailMessage:
    return EmailMessage(
        message_id=data["message_id"],
        thread_id=data.get("thread_id", ""),
        internal_date_ms=int(data.get("internal_date_ms", 0)),
        from_addr=data.get("from_addr", ""),
        from_email=data.get("from_email", ""),
        subject=data.get("subject", ""),
        date_header=data.get("date_header", ""),
        snippet=data.get("snippet", ""),
        labels=data.get("labels", []),
        body_text=data.get("body_text", ""),
        category=data.get("category"),
    )


def load_archived_messages_index(config: AppConfig) -> dict[str, EmailMessage]:
    """Map Gmail message IDs to locally archived EmailMessage objects."""
    base = config.resolve(config.paths.emails)
    if not base.exists():
        return {}

    index: dict[str, EmailMessage] = {}
    for meta_file in base.rglob("*.meta.json"):
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        message_id = data.get("message_id")
        if message_id:
            index[message_id] = _meta_to_message(data)
    return index


def load_messages_for_date(config: AppConfig, report_date: date) -> list[EmailMessage]:
    dest = emails_dir(config, report_date)
    if not dest.exists():
        return []

    messages: list[EmailMessage] = []
    for meta_file in sorted(dest.glob("*.meta.json")):
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        messages.append(_meta_to_message(data))
    return messages


def iter_archived_dates(config: AppConfig) -> list[date]:
    """Return report dates that have at least one archived email."""
    base = config.resolve(config.paths.emails)
    if not base.exists():
        return []

    dates: set[date] = set()
    for meta_file in base.rglob("*.meta.json"):
        try:
            dates.add(date.fromisoformat(meta_file.parent.name))
        except ValueError:
            continue
    return sorted(dates)


def update_message_category(
    config: AppConfig,
    report_date: date,
    message_id: str,
    category: str,
) -> None:
    meta_path = _meta_path(emails_dir(config, report_date), message_id)
    if not meta_path.exists():
        return
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["category"] = category
    meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
