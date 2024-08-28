"""Persist fetched emails to disk."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from email_analyzer.config import AppConfig
from email_analyzer.gmail.auth import build_gmail_service
from email_analyzer.gmail.fetch import EmailMessage, download_raw_eml
from email_analyzer.storage.paths import emails_dir


def _meta_path(dest: Path, message_id: str) -> Path:
    return dest / f"{message_id}.meta.json"


def _eml_path(dest: Path, message_id: str) -> Path:
    return dest / f"{message_id}.eml"


def message_to_meta(msg: EmailMessage) -> dict:
    data = asdict(msg)
    data["internal_datetime"] = msg.internal_datetime.isoformat()
    return data


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

    if not eml_path.exists():
        service = build_gmail_service(config, interactive=interactive)
        eml_path.write_bytes(download_raw_eml(service, msg.message_id))

    meta_path.write_text(
        json.dumps(message_to_meta(msg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
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
        saved.append(dest)
    return saved



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
