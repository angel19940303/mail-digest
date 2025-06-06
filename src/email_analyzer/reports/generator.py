"""Generate daily, weekly, and monthly reports."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from email_analyzer.config import AppConfig
from email_analyzer.gmail.fetch import EmailMessage
from email_analyzer.reports.ai_cli import prompt_file_for_mode, run_prompt
from email_analyzer.storage.paths import (
    daily_report_path,
    iso_week_label,
    monthly_report_path,
    report_date_parts,
    weekly_report_path,
)

NO_EMAILS_REPORT = """# Daily Email Report — {date}

> **Emails analyzed**: 0 total (newsletter: 0, community: 0, other: 0)

## Newsletter

### New tools
_None_

### Improvements / trends
_None_

## Community

### Highlights
_No community emails in this window._

### Notable threads / announcements
_None_

## Other

### Summary
No emails were received in this reporting window.

### Notable emails
_None_

### Action items
_None_
"""






def _truncate_body(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."

def _format_email_block(msg: EmailMessage, max_body: int) -> str:
    raw = msg.body_text or msg.snippet or ""
    truncated = len(raw) > max_body
    body = _truncate_body(raw, max_body)
    trunc_note = " (body truncated)" if truncated else ""
    return (
        f"---\n"
        f"Category: {msg.category or 'unknown'}\n"
        f"From: {msg.from_addr}\n"
        f"Subject: {msg.subject}\n"
        f"Date: {msg.date_header}\n"
        f"Snippet: {msg.snippet}\n"
        f"Body{trunc_note}:\n{body}\n"
    )


def build_daily_input(config: AppConfig, messages: list[EmailMessage], report_date: date) -> str:
    _, _, yyyymmdd = report_date_parts(report_date)
    max_body = config.ai.max_body_chars_per_email
    by_cat: dict[str, list[EmailMessage]] = {
        "newsletter": [],
        "community": [],
        "other": [],
    }
    for msg in messages:
        cat = msg.category or "other"
        by_cat.setdefault(cat, []).append(msg)

    lines = [
        f"Report date: {yyyymmdd}",
        f"Total emails: {len(messages)}",
        f"Counts: newsletter={len(by_cat['newsletter'])}, "
        f"community={len(by_cat['community'])}, other={len(by_cat['other'])}",
        "",
        "Write a RICH detailed report for archival. Include specifics from each email below.",
        "",
    ]
    for cat in ("newsletter", "community", "other"):
        lines.append(f"### {cat.title()} ({len(by_cat.get(cat, []))})")
        for msg in by_cat.get(cat, []):
            lines.append(_format_email_block(msg, max_body))
        lines.append("")
    return "\n".join(lines)






def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return t

def _check_ai_output(stdout: str | None, stderr: str | None, code: int, label: str) -> str:
    out = stdout or ""
    if code != 0 or not out.strip():
        detail = stderr or "no output from AI CLI"
        raise RuntimeError(f"{label} failed (exit {code}): {detail}")
    return out


def generate_daily_report(
    config: AppConfig,
    messages: list[EmailMessage],
    report_date: date,
) -> tuple[str, Path]:
    _, _, yyyymmdd = report_date_parts(report_date)
    out_path = daily_report_path(config, report_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not messages:
        content = NO_EMAILS_REPORT.format(date=yyyymmdd)
        out_path.write_text(content, encoding="utf-8")
        return content, out_path

    user_input = build_daily_input(config, messages, report_date)
    stdout, stderr, code = run_prompt(
        config,
        user_input,
        system_prompt_file=prompt_file_for_mode(config, "daily"),
        mode="report",
    )
    stdout = _check_ai_output(stdout, stderr, code, "Daily report generation")

    content = _strip_fences(stdout)
    if not content.startswith("#"):
        content = f"# Daily Email Report — {yyyymmdd}\n\n{content}"
    out_path.write_text(content, encoding="utf-8")
    return content, out_path


def _load_daily_reports_in_range(
    config: AppConfig,
    start: date,
    end: date,
) -> list[tuple[date, str]]:
    reports: list[tuple[date, str]] = []
    current = start
    while current <= end:
        path = daily_report_path(config, current)
        if path.exists():
            reports.append((current, path.read_text(encoding="utf-8")))
        current += timedelta(days=1)
    return reports


def _week_range_for_sunday(sunday: date) -> tuple[date, date]:
    """Monday through Sunday for the week ending on given Sunday."""
    monday = sunday - timedelta(days=6)
    return monday, sunday


def generate_weekly_report(config: AppConfig, week_end: date) -> tuple[str, Path]:
    monday, sunday = _week_range_for_sunday(week_end)
    reports = _load_daily_reports_in_range(config, monday, sunday)
    label = iso_week_label(week_end)
    out_path = weekly_report_path(config, week_end)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not reports:
        content = f"# Weekly Email Report — {label}\n\nNo daily reports available for this week."
        out_path.write_text(content, encoding="utf-8")
        return content, out_path

    user_input = f"Week: {label}\n\n" + "\n\n---\n\n".join(
        f"## Daily report {d.isoformat()}\n{text}" for d, text in reports
    )
    stdout, stderr, code = run_prompt(
        config,
        user_input,
        system_prompt_file=prompt_file_for_mode(config, "weekly"),
        mode="weekly",
    )
    if code != 0 or not (stdout or "").strip():
        raise RuntimeError(f"Weekly report generation failed (exit {code}): {stderr or 'no output'}")

    content = _strip_fences(stdout)
    if not content.startswith("#"):
        content = f"# Weekly Email Report — {label}\n\n{content}"
    out_path.write_text(content, encoding="utf-8")
    return content, out_path


def generate_monthly_report(config: AppConfig, month_end: date) -> tuple[str, Path]:
    first = month_end.replace(day=1)
    reports = _load_daily_reports_in_range(config, first, month_end)
    yyyymm = f"{month_end.year:04d}-{month_end.month:02d}"
    out_path = monthly_report_path(config, month_end)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not reports:
        content = f"# Monthly Email Report — {yyyymm}\n\nNo daily reports available for this month."
        out_path.write_text(content, encoding="utf-8")
        return content, out_path

    user_input = f"Month: {yyyymm}\n\n" + "\n\n---\n\n".join(
        f"## Daily report {d.isoformat()}\n{text}" for d, text in reports
    )
    stdout, stderr, code = run_prompt(
        config,
        user_input,
        system_prompt_file=prompt_file_for_mode(config, "monthly"),
        mode="monthly",
    )
    if code != 0 or not (stdout or "").strip():
        raise RuntimeError(f"Monthly report generation failed (exit {code}): {stderr or 'no output'}")

    content = _strip_fences(stdout)
    if not content.startswith("#"):
        content = f"# Monthly Email Report — {yyyymm}\n\n{content}"
    out_path.write_text(content, encoding="utf-8")
    return content, out_path


def is_last_day_of_month(d: date) -> bool:
    return (d + timedelta(days=1)).month != d.month
