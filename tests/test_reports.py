from datetime import date
from unittest.mock import patch

from email_analyzer.config import AppConfig, GmailConfig, PathsConfig, ScheduleConfig, SenderRules
from email_analyzer.gmail.fetch import EmailMessage
from email_analyzer.reports.generator import (
    combine_daily_report,
    generate_daily_report,
)


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        schedule=ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=GmailConfig(),
        paths=PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=SenderRules(),
    )


def _msg(message_id: str, *, category: str, subject: str) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        thread_id="t",
        internal_date_ms=0,
        from_addr=f"{category}@example.com",
        from_email=f"{category}@example.com",
        subject=subject,
        date_header="",
        snippet="",
        body_text=f"body of {subject}",
        category=category,
    )


def test_combine_daily_report_structure():
    content = combine_daily_report(
        date(2026, 6, 11),
        {"newsletter": 2, "community": 1, "other": 3},
        {
            "newsletter": "### New tools\n- Tool A",
            "community": "### Highlights\nMeetup",
            "other": "### Summary\nReceipts",
        },
    )
    assert content.startswith("# Daily Email Report — 2026-06-11\n")
    assert "**Emails analyzed**: 6 total (newsletter: 2, community: 1, other: 3)" in content
    assert "## Newsletter\n### New tools\n- Tool A" in content
    assert "## Community\n### Highlights\nMeetup" in content
    assert "## Other\n### Summary\nReceipts" in content
    assert content.count("# Daily Email Report") == 1


def test_combine_strips_model_title_via_generate(tmp_path):
    config = _config(tmp_path)
    messages = [_msg("n1", category="newsletter", subject="TLDR AI")]

    def fake_run_prompt(_config, user_input, *, system_prompt_file=None, mode="report"):
        return (
            "# Daily Email Report — 2026-06-11\n\n"
            "## Newsletter\n\n"
            "### New tools\n- Tool A\n",
            "",
            0,
        )

    with patch("email_analyzer.reports.generator.run_prompt", side_effect=fake_run_prompt) as mock_run:
        content, path = generate_daily_report(config, messages, date(2026, 6, 11))

    assert path.exists()
    assert content.startswith("# Daily Email Report — 2026-06-11\n")
    assert content.count("# Daily Email Report") == 1
    assert "## Newsletter" in content
    assert "### New tools" in content
    assert "- Tool A" in content
    assert mock_run.call_count == 1


def test_empty_buckets_skip_run_prompt(tmp_path):
    config = _config(tmp_path)
    with patch("email_analyzer.reports.generator.run_prompt") as mock_run:
        content, _path = generate_daily_report(config, [], date(2026, 6, 11))

    mock_run.assert_not_called()
    assert "newsletter: 0, community: 0, other: 0" in content
    assert "### New tools" in content
    assert "_No community emails in this window._" in content
    assert "No emails were received in this reporting window." in content


def test_nonempty_buckets_call_run_prompt_once_each(tmp_path):
    config = _config(tmp_path)
    messages = [
        _msg("n1", category="newsletter", subject="AlphaSignal digest"),
        _msg("c1", category="community", subject="Boost thread"),
        _msg("o1", category="other", subject="Receipt"),
    ]

    def fake_run_prompt(_config, user_input, *, system_prompt_file=None, mode="report"):
        return (f"### Summary from {mode}\n- ok", "", 0)

    with patch("email_analyzer.reports.generator.run_prompt", side_effect=fake_run_prompt) as mock_run:
        content, _path = generate_daily_report(config, messages, date(2026, 6, 11))

    assert mock_run.call_count == 3
    modes = [call.kwargs["mode"] for call in mock_run.call_args_list]
    assert modes == ["newsletter", "community", "other"]
    inputs = [call.args[1] for call in mock_run.call_args_list]
    assert "AlphaSignal digest" in inputs[0]
    assert "Boost thread" not in inputs[0]
    assert "Receipt" not in inputs[0]
    assert "Boost thread" in inputs[1]
    assert "AlphaSignal digest" not in inputs[1]
    assert "Receipt" in inputs[2]
    assert "AlphaSignal digest" not in inputs[2]
    assert "newsletter: 1, community: 1, other: 1" in content
    assert "### Summary from newsletter" in content
    assert "### Summary from community" in content
    assert "### Summary from other" in content


def test_only_newsletter_skips_other_ai_calls(tmp_path):
    config = _config(tmp_path)
    messages = [_msg("n1", category="newsletter", subject="TLDR AI")]

    with patch(
        "email_analyzer.reports.generator.run_prompt",
        return_value=("### New tools\n- Tool A", "", 0),
    ) as mock_run:
        content, _path = generate_daily_report(config, messages, date(2026, 6, 11))

    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs["mode"] == "newsletter"
    assert "_No other emails in this window._" in content
    assert "_No community emails in this window._" in content
