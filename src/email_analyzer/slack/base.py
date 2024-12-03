"""Slack notifier protocol for webhook today, bot later."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ReportSummary:
    report_date: str
    newsletter_bullets: list[str] = field(default_factory=list)
    community_bullets: list[str] = field(default_factory=list)
    other_bullets: list[str] = field(default_factory=list)
    report_path: Path | None = None
    error: str | None = None


class ReportNotifier(Protocol):
    def send_daily(self, summary: ReportSummary) -> None: ...

    def send_error(self, message: str) -> None: ...
