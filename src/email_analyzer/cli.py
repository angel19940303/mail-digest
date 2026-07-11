"""Command-line interface."""

from __future__ import annotations

import argparse
from datetime import date

from email_analyzer.config import load_config
from email_analyzer.gmail.auth import _run_browser_login
from email_analyzer.classify.hybrid import classify_messages, reclassify_archived
from email_analyzer.jobs.daily import run_job, setup_logging
from email_analyzer.reports.generator import generate_daily_report
from email_analyzer.storage.emails import iter_archived_dates, load_messages_for_date


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
        help="Fail instead of prompting for browser sign-in when Gmail token is invalid",
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
    parser = argparse.ArgumentParser(description="Mail Digest — Gmail to Slack summaries")
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

    reclassify_parser = sub.add_parser(
        "reclassify",
        help="Re-apply sender rules to archived emails on disk",
    )
    reclassify_parser.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        help="Report date (YYYY-MM-DD); omit with --all to process every archived date",
    )
    reclassify_parser.add_argument(
        "--all",
        action="store_true",
        help="Reclassify every archived date",
    )
    reclassify_parser.add_argument(
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
        messages = classify_messages(config, messages, args.date)
        _, path = generate_daily_report(config, messages, args.date)
        print(f"Regenerated report: {path}")
        return

    if args.command == "reclassify":
        config = load_config(args.root)
        setup_logging(config)
        if args.all:
            dates = iter_archived_dates(config)
        elif args.date is not None:
            dates = [args.date]
        else:
            raise SystemExit("Provide --date YYYY-MM-DD or --all")

        total_changed = 0
        for d in dates:
            counts, changed = reclassify_archived(config, d)
            total_changed += changed
            print(
                f"{d.isoformat()}: "
                f"newsletter={counts['newsletter']}, "
                f"community={counts['community']}, "
                f"other={counts['other']} "
                f"({changed} updated)"
            )
        print(f"Done. {total_changed} categor{'y' if total_changed == 1 else 'ies'} updated.")
        return

    if args.command == "auth":
        config = load_config(args.root)
        _run_browser_login(config)
        print(f"Token saved to {config.token_path}")
        return

    if args.command in ("run", "trigger"):
        raise SystemExit(_run_job_command(args))


if __name__ == "__main__":
    main()
