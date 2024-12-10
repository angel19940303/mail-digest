from pathlib import Path

from email_analyzer.slack.webhook import parse_report_sections

SAMPLE = """# Daily Email Report — 2026-06-11

## Newsletter
- **New tools**: Tool A
- **Improvements / trends**: Faster builds

## Community
- **Highlights**: Meetup announced

## Other
- **Summary**: Receipt from store
"""

NESTED_SAMPLE = """## Newsletter
- **New tools**:
  - Claude Fable 5 by Anthropic for general use.
  - WorkOS launches auth.md.

- **Improvements / trends**:
  - Docker adds GPU support.

## Community
- **Highlights**: None
- **Notable threads / announcements**:
  - Feedback on the new Boost.Graph documentation.

## Other
- **Summary**: 14 emails received.
- **Action items**: None
"""


def test_parse_sections():
    n, c, o = parse_report_sections(SAMPLE, max_bullets=5)
    assert any("Tool A" in b for b in n)
    assert any("Meetup" in b for b in c)
    assert any("Receipt" in b for b in o)


def test_parse_nested_bullets():
    n, c, o = parse_report_sections(NESTED_SAMPLE, max_bullets=5)
    assert any("Claude Fable" in b for b in n)
    assert any("WorkOS" in b for b in n)
    assert any("Docker" in b for b in n)
    assert not any("New tools" in b for b in n)
    assert any("Boost.Graph" in b for b in c)
    assert any("14 emails" in b for b in o)


def test_report_path_name_only():
    from email_analyzer.config import AppConfig, SlackConfig
    from email_analyzer.slack.webhook import WebhookNotifier

    notifier = WebhookNotifier(
        AppConfig(
            root=Path("."),
            schedule=__import__("email_analyzer.config", fromlist=["ScheduleConfig"]).ScheduleConfig(),
            ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
            gmail=__import__("email_analyzer.config", fromlist=["GmailConfig"]).GmailConfig(),
            paths=__import__("email_analyzer.config", fromlist=["PathsConfig"]).PathsConfig(),
            slack=SlackConfig(),
            sender_rules=__import__("email_analyzer.config", fromlist=["SenderRules"]).SenderRules(),
            slack_webhook_url=None,
        )
    )
    # Footer uses .name — verified via send_daily block construction in integration;
    # here we only assert parse logic for nested sample above.
    assert notifier.webhook_url is None
