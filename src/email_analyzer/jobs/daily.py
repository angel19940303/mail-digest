"""Daily job: fetch → classify → report → Slack."""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime

from email_analyzer.classify.hybrid import classify_messages
from email_analyzer.config import AppConfig, load_config
from email_analyzer.gmail.fetch import fetch_messages_in_window
from email_analyzer.reports.generator import (
    generate_daily_report,
    generate_monthly_report,
    generate_weekly_report,
    is_last_day_of_month,
)
from email_analyzer.slack.webhook import WebhookNotifier, summary_from_markdown
from email_analyzer.storage.emails import save_messages
from email_analyzer.storage.paths import compute_window, report_date_parts

logger = logging.getLogger(__name__)


def run_job(
    config: AppConfig | None = None,
    *,
    report_date: date | None = None,
    interactive: bool = True,
) -> int:
    config = config or load_config()
    window_start, window_end, rd = compute_window(config, report_date=report_date)

    _, _, yyyymmdd = report_date_parts(rd)
    notifier = WebhookNotifier(config)

    try:
        logger.info(
            "Fetching emails window %s -> %s (report %s)",
            window_start.isoformat(),
            window_end.isoformat(),
            yyyymmdd,
        )
        messages = fetch_messages_in_window(
            config,
            window_start,
            window_end,
            interactive=interactive,
        )
        logger.info("Fetched %d messages", len(messages))

        save_messages(config, rd, messages, interactive=interactive)
        messages = classify_messages(config, messages, rd)

        content, report_path = generate_daily_report(config, messages, rd)
        summary = summary_from_markdown(content, yyyymmdd, report_path, config)
        notifier.send_daily(summary)
        logger.info("Daily report saved: %s", report_path)
        if rd.weekday() == 6:  # Sunday
            _, weekly_path = generate_weekly_report(config, rd)
            logger.info("Weekly report saved: %s", weekly_path)

        if is_last_day_of_month(rd):
            _, monthly_path = generate_monthly_report(config, rd)
            logger.info("Monthly report saved: %s", monthly_path)

        return 0
    except Exception as exc:
        logger.exception("Job failed")
        try:
            notifier.send_error(f"Email Analyzer failed for {yyyymmdd}: {exc}")
        except Exception:
            logger.exception("Failed to send Slack error notification")
        return 1


def setup_logging(config: AppConfig) -> None:
    log_dir = config.resolve("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now().date().isoformat()}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
