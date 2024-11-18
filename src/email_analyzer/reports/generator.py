"""Generate daily reports."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from email_analyzer.config import AppConfig
from email_analyzer.gmail.fetch import EmailMessage
from email_analyzer.reports.ai_cli import prompt_file_for_mode, run_prompt
from email_analyzer.storage.paths import daily_report_path, report_date_parts

NO_EMAILS_REPORT = """# Daily Email Report — {date}

> **Emails analyzed**: 0 total (newsletter: 0, community: 0, other: 0)

## Newsletter

### New tools
_None_

## Community

### Highlights
_No community emails in this window._

## Other

### Summary
No emails were received in this reporting window.
"""


def _format_email_block(msg: EmailMessage, max_body: int) -> str:
    body = msg.body_text or msg.snippet or ""
    return (
        f"---\n"
        f"Category: {msg.category or 'unknown'}\n"
        f"From: {msg.from_addr}\n"
        f"Subject: {msg.subject}\n"
        f"Date: {msg.date_header}\n"
        f"Snippet: {msg.snippet}\n"
        f"Body:\n{body}\n"
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

    content = stdout.strip()
    if not content.startswith("#"):
        content = f"# Daily Email Report — {yyyymmdd}\n\n{content}"
    out_path.write_text(content, encoding="utf-8")
    return content, out_path
