"""Generate daily, weekly, and monthly reports."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from email_analyzer.classify.rules import CATEGORIES, group_messages_by_category
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

NEWSLETTER_STUB = """### New tools
_None_

### Improvements / trends
_None_"""

COMMUNITY_STUB = """### Highlights
_No community emails in this window._

### Notable threads / announcements
_None_"""

OTHER_STUB = """### Summary
No emails were received in this reporting window.

### Notable emails
_None_

### Action items
_None_"""

OTHER_EMPTY_STUB = """### Summary
_No other emails in this window._

### Notable emails
_None_

### Action items
_None_"""

CATEGORY_STUBS = {
    "newsletter": NEWSLETTER_STUB,
    "community": COMMUNITY_STUB,
    "other": OTHER_STUB,
}

_H2_CATEGORY = re.compile(r"^##\s+(Newsletter|Community|Other)\s*$", re.IGNORECASE)
_H1_TITLE = re.compile(r"^#\s+")
_EXPECTED_HEADINGS = {
    "newsletter": ("### New tools", "### Improvements / trends"),
    "community": ("### Highlights", "### Notable threads / announcements"),
    "other": ("### Summary", "### Notable emails", "### Action items"),
}


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


def build_category_input(
    config: AppConfig,
    messages: list[EmailMessage],
    report_date: date,
    category: str,
) -> str:
    _, _, yyyymmdd = report_date_parts(report_date)
    max_body = config.ai.max_body_chars_per_email
    lines = [
        f"Report date: {yyyymmdd}",
        f"Category: {category}",
        f"Email count: {len(messages)}",
        "",
        "Write a RICH detailed section for archival. Use only the emails below.",
        "",
    ]
    for msg in messages:
        lines.append(_format_email_block(msg, max_body))
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


def _normalize_section_output(text: str, category: str) -> str:
    """Strip titles/H2 wrappers so Python owns the report structure."""
    text = _strip_fences(text)
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _H1_TITLE.match(lines[0].lstrip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    lines = [ln for ln in lines if not _H2_CATEGORY.match(ln.strip())]
    body = "\n".join(lines).strip()
    expected = _EXPECTED_HEADINGS.get(category, ())
    if body and expected:
        lowered = body.lower()
        if not any(heading.lower() in lowered for heading in expected):
            body = f"{expected[0]}\n{body}"
    return body


def _check_ai_output(stdout: str | None, stderr: str | None, code: int, label: str) -> str:
    out = stdout or ""
    if code != 0 or not out.strip():
        detail = stderr or "no output from AI CLI"
        raise RuntimeError(f"{label} failed (exit {code}): {detail}")
    return out


def summarize_category(
    config: AppConfig,
    messages: list[EmailMessage],
    report_date: date,
    category: str,
    *,
    empty_stub: str | None = None,
) -> str:
    if not messages:
        return empty_stub if empty_stub is not None else CATEGORY_STUBS[category]
    user_input = build_category_input(config, messages, report_date, category)
    stdout, stderr, code = run_prompt(
        config,
        user_input,
        system_prompt_file=prompt_file_for_mode(config, category),
        mode=category,
    )
    stdout = _check_ai_output(stdout, stderr, code, f"{category.title()} section generation")
    return _normalize_section_output(stdout, category)


def combine_daily_report(
    report_date: date,
    counts: dict[str, int],
    sections: dict[str, str],
) -> str:
    _, _, yyyymmdd = report_date_parts(report_date)
    newsletter = counts.get("newsletter", 0)
    community = counts.get("community", 0)
    other = counts.get("other", 0)
    total = newsletter + community + other
    return (
        f"# Daily Email Report — {yyyymmdd}\n\n"
        f"> **Emails analyzed**: {total} total "
        f"(newsletter: {newsletter}, community: {community}, other: {other})\n\n"
        f"## Newsletter\n{sections['newsletter'].strip()}\n\n"
        f"## Community\n{sections['community'].strip()}\n\n"
        f"## Other\n{sections['other'].strip()}\n"
    )


def generate_daily_report(
    config: AppConfig,
    messages: list[EmailMessage],
    report_date: date,
) -> tuple[str, Path]:
    out_path = daily_report_path(config, report_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    by_cat = group_messages_by_category(messages)
    counts = {cat: len(by_cat.get(cat, [])) for cat in CATEGORIES}
    sections = {
        cat: summarize_category(
            config,
            by_cat.get(cat, []),
            report_date,
            cat,
            empty_stub=OTHER_EMPTY_STUB if cat == "other" and messages else None,
        )
        for cat in CATEGORIES
    }
    content = combine_daily_report(report_date, counts, sections)
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
