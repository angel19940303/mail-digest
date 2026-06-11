"""Post report summaries to Slack via incoming webhook."""

from __future__ import annotations

import re

import httpx

from email_analyzer.config import AppConfig
from email_analyzer.slack.base import ReportNotifier, ReportSummary

_SECTION_HEADERS = {
    "newsletter": re.compile(r"^##\s+Newsletter\s*$", re.IGNORECASE | re.MULTILINE),
    "community": re.compile(r"^##\s+Community\s*$", re.IGNORECASE | re.MULTILINE),
    "other": re.compile(r"^##\s+Other\s*$", re.IGNORECASE | re.MULTILINE),
}

_SKIP_VALUES = frozenset({"none", "n/a"})


def _strip_markdown(text: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", text).strip()


def _normalize_bullet_line(line: str) -> str | None:
    """Turn a markdown bullet line into plain text for Slack, or skip."""
    stripped = line.strip()
    if not (stripped.startswith("- ") or stripped.startswith("* ")):
        return None

    item = _strip_markdown(stripped[2:].strip())
    if not item:
        return None

    # Sub-header only, e.g. "- **New tools**:"
    if item.endswith(":") and ":" not in item[:-1]:
        return None

    # "Label: value" — use value when present
    if ": " in item:
        _label, _, value = item.partition(": ")
        value = value.strip()
        if not value or value.lower() in _SKIP_VALUES:
            return None
        return value

    if item.lower() in _SKIP_VALUES:
        return None
    return item


def parse_report_sections(markdown: str, max_bullets: int) -> tuple[list[str], list[str], list[str]]:
    """Extract bullet highlights from each report section."""
    sections: dict[str, str] = {}
    positions: list[tuple[str, int]] = []
    for name, pattern in _SECTION_HEADERS.items():
        match = pattern.search(markdown)
        if match:
            positions.append((name, match.start()))
    positions.sort(key=lambda x: x[1])

    for i, (name, start) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(markdown)
        sections[name] = markdown[start:end]

    def bullets(text: str) -> list[str]:
        found: list[str] = []
        for line in text.splitlines():
            item = _normalize_bullet_line(line)
            if item:
                found.append(item)
            if len(found) >= max_bullets:
                break
        return found

    return (
        bullets(sections.get("newsletter", "")),
        bullets(sections.get("community", "")),
        bullets(sections.get("other", "")),
    )


def summary_from_markdown(
    markdown: str,
    report_date: str,
    report_path,
    config: AppConfig,
) -> ReportSummary:
    n, c, o = parse_report_sections(markdown, config.slack.max_bullets_per_section)
    return ReportSummary(
        report_date=report_date,
        newsletter_bullets=n,
        community_bullets=c,
        other_bullets=o,
        report_path=report_path,
    )


def _format_bullets(items: list[str], max_chars: int) -> str:
    if not items:
        return "_None_"
    text = "\n".join(f"• {item}" for item in items)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


class WebhookNotifier:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.webhook_url = config.slack_webhook_url

    def send_daily(self, summary: ReportSummary) -> None:
        if not self.webhook_url:
            return
        max_chars = self.config.slack.max_chars_per_block
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Daily Email Report — {summary.report_date}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Newsletter*\n{_format_bullets(summary.newsletter_bullets, max_chars)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Community*\n{_format_bullets(summary.community_bullets, max_chars)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Other*\n{_format_bullets(summary.other_bullets, max_chars)}",
                },
            },
        ]
        if summary.report_path:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Full report: `{summary.report_path.name}`",
                        }
                    ],
                }
            )
        payload = {"blocks": blocks}
        httpx.post(self.webhook_url, json=payload, timeout=30).raise_for_status()

    def send_error(self, message: str) -> None:
        if not self.webhook_url:
            return
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Mail Digest — Error"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message[: self.config.slack.max_chars_per_block]},
                },
            ]
        }
        httpx.post(self.webhook_url, json=payload, timeout=30).raise_for_status()


def get_notifier(config: AppConfig) -> ReportNotifier:
    return WebhookNotifier(config)
