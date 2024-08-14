from datetime import date
from pathlib import Path

from email_analyzer.config import AppConfig, PathsConfig, ScheduleConfig
from email_analyzer.storage.paths import (
    compute_window,
    daily_report_path,
    emails_dir,
    iso_week_label,
    monthly_report_path,
    weekly_report_path,
)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=ScheduleConfig(run_hour=18, run_minute=0, window_hours=24),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=__import__("email_analyzer.config", fromlist=["GmailConfig"]).GmailConfig(),
        paths=PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
    )


def test_emails_dir_structure(tmp_path):
    config = _config(tmp_path)
    d = date(2026, 6, 11)
    path = emails_dir(config, d)
    assert path == tmp_path / "emails" / "2026" / "2026-06" / "2026-06-11"


def test_report_paths(tmp_path):
    config = _config(tmp_path)
    d = date(2026, 6, 11)
    assert daily_report_path(config, d) == tmp_path / "daily_reports" / "2026" / "2026-06" / "2026-06-11.md"
    assert weekly_report_path(config, d).name == f"{iso_week_label(d)}.md"
    assert monthly_report_path(config, d) == tmp_path / "monthly_report" / "2026" / "2026-06.md"


def test_compute_window_uses_run_hour(tmp_path):
    config = _config(tmp_path)
    rd = date(2026, 6, 11)
    start, end, report_date = compute_window(config, report_date=rd)
    assert report_date == rd
    assert end.hour == 18
    assert (end - start).total_seconds() == 24 * 3600
