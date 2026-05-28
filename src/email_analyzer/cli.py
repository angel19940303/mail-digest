"""Command-line interface."""

from __future__ import annotations

import argparse
from datetime import date

from email_analyzer.config import load_config
from email_analyzer.gmail.auth import authenticate
from email_analyzer.jobs.daily import run_job, setup_logging
from email_analyzer.reports.generator import generate_daily_report
from email_analyzer.storage.emails import load_messages_for_date


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _add_job_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        help="Report date (YYYY-MM-DD) for backfill; window ends 6pm that day",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Project root directory",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of opening browser for OAuth",
    )


def _run_job_command(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    setup_logging(config)
    return run_job(
        config,
        report_date=args.date,
        interactive=not args.non_interactive,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Email Analyzer — Gmail to Slack reports")
    sub = parser.add_subparsers(dest="command", required=True)

    auth_parser = sub.add_parser("auth", help="Run Gmail OAuth flow and save token.json")
    auth_parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Project root directory",
    )

    run_parser = sub.add_parser("run", help="Run daily fetch, analyze, and report job")
    _add_job_args(run_parser)


    regen_parser = sub.add_parser(
        "regenerate",
        help="Regenerate daily report from archived emails on disk (no Gmail fetch)",
    )
    regen_parser.add_argument(
        "--date",
        type=_parse_date,
        required=True,
        help="Report date (YYYY-MM-DD)",
    )
    regen_parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Project root directory",
    )

    trigger_parser = sub.add_parser(
        "trigger",
        help="Manually trigger fetch, analyze, report, and Slack (same as run)",
    )
    _add_job_args(trigger_parser)

    args = parser.parse_args()


    if args.command == "regenerate":
        config = load_config(args.root)
        setup_logging(config)
        messages = load_messages_for_date(config, args.date)
        _, path = generate_daily_report(config, messages, args.date)
        print(f"Regenerated report: {path}")
        return

    if args.command == "auth":
        config = load_config(args.root)
        authenticate(config, interactive=True)
        print(f"Token saved to {config.token_path}")
        return

    if args.command in ("run", "trigger"):
        raise SystemExit(_run_job_command(args))


if __name__ == "__main__":
    main()
