"""Path helpers for emails and reports."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from email_analyzer.config import AppConfig


def local_tz() -> ZoneInfo:
    return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def report_date_parts(d: date) -> tuple[str, str, str]:
    """Return YYYY, YYYY-MM, YYYY-MM-DD strings."""
    yyyy = f"{d.year:04d}"
    yyyymm = f"{d.year:04d}-{d.month:02d}"
    yyyymmdd = f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    return yyyy, yyyymm, yyyymmdd


def iso_week_label(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def compute_window(
    config: AppConfig,
    *,
    run_at: datetime | None = None,
    report_date: date | None = None,
) -> tuple[datetime, datetime, date]:
    """
    Compute rolling fetch window ending at run_hour:run_minute on report_date.

  Returns (window_start, window_end, report_date).
    """
    tz = local_tz()
    now = run_at or datetime.now(tz)

    if report_date is not None:
        window_end = datetime(
            report_date.year,
            report_date.month,
            report_date.day,
            config.schedule.run_hour,
            config.schedule.run_minute,
            tzinfo=tz,
        )
    else:
        window_end = now.replace(
            hour=config.schedule.run_hour,
            minute=config.schedule.run_minute,
            second=0,
            microsecond=0,
        )
        if now < window_end:
            window_end -= timedelta(days=1)

    window_start = window_end - timedelta(hours=config.schedule.window_hours)
    rd = window_end.date()
    return window_start, window_end, rd


def emails_dir(config: AppConfig, report_date: date) -> Path:
    yyyy, yyyymm, yyyymmdd = report_date_parts(report_date)
    return config.resolve(config.paths.emails) / yyyy / yyyymm / yyyymmdd


def daily_report_path(config: AppConfig, report_date: date) -> Path:
    yyyy, yyyymm, yyyymmdd = report_date_parts(report_date)
    return config.resolve(config.paths.daily_reports) / yyyy / yyyymm / f"{yyyymmdd}.md"


def weekly_report_path(config: AppConfig, week_end: date) -> Path:
    label = iso_week_label(week_end)
    yyyy = f"{week_end.year:04d}"
    return config.resolve(config.paths.weekly_reports) / yyyy / f"{label}.md"


def monthly_report_path(config: AppConfig, month_end: date) -> Path:
    yyyy = f"{month_end.year:04d}"
    yyyymm = f"{month_end.year:04d}-{month_end.month:02d}"
    return config.resolve(config.paths.monthly_reports) / yyyy / f"{yyyymm}.md"


def logs_dir(config: AppConfig) -> Path:
    return config.resolve("logs")


def prompts_dir(config: AppConfig) -> Path:
    return config.resolve("prompts")
