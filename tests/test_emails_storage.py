import json
from datetime import date
from pathlib import Path

from email_analyzer.config import AppConfig, PathsConfig, ScheduleConfig
from email_analyzer.storage.emails import load_messages_for_date, purge_old_archives


def _config(tmp_path: Path, *, retention_days: int = 30) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=__import__("email_analyzer.config", fromlist=["GmailConfig"]).GmailConfig(),
        paths=PathsConfig(email_retention_days=retention_days),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
    )


def _write_archive(root: Path, report_date: date, message_id: str = "abc") -> Path:
    dest = root / "emails" / f"{report_date.year:04d}" / f"{report_date.year:04d}-{report_date.month:02d}" / report_date.isoformat()
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{message_id}.meta.json").write_text(
        json.dumps({"message_id": message_id}),
        encoding="utf-8",
    )
    (dest / f"{message_id}.eml").write_bytes(b"raw")
    return dest


def test_purge_old_archives_removes_expired_dirs(tmp_path):
    config = _config(tmp_path, retention_days=30)
    old = _write_archive(tmp_path, date(2026, 4, 1))
    keep = _write_archive(tmp_path, date(2026, 6, 1))

    removed = purge_old_archives(config, today=date(2026, 6, 11))

    assert removed == 1
    assert not old.exists()
    assert keep.exists()


def test_purge_old_archives_disabled_when_zero(tmp_path):
    config = _config(tmp_path, retention_days=0)
    old = _write_archive(tmp_path, date(2026, 1, 1))

    assert purge_old_archives(config, today=date(2026, 6, 11)) == 0
    assert old.exists()


def test_load_messages_missing_list_headers(tmp_path):
    config = _config(tmp_path)
    dest = _write_archive(tmp_path, date(2026, 6, 11), "abc")
    (dest / "abc.meta.json").write_text(
        json.dumps(
            {
                "message_id": "abc",
                "thread_id": "t",
                "internal_date_ms": 0,
                "from_addr": "a@example.com",
                "from_email": "a@example.com",
                "subject": "Hi",
                "date_header": "",
                "snippet": "",
                "body_text": "hello",
            }
        ),
        encoding="utf-8",
    )
    messages = load_messages_for_date(config, date(2026, 6, 11))
    assert len(messages) == 1
    assert messages[0].list_id == ""
    assert messages[0].list_unsubscribe == ""
    assert messages[0].precedence == ""
    assert messages[0].category is None
