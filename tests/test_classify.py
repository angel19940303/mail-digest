from email_analyzer.classify.rules import (
    classify_by_rules,
    classify_message,
    group_messages_by_category,
)
from email_analyzer.config import AppConfig, NewsletterPattern, SenderRules
from email_analyzer.gmail.fetch import EmailMessage


def _config(rules: SenderRules) -> AppConfig:
    return AppConfig(
        root=__import__("pathlib").Path("."),
        schedule=__import__("email_analyzer.config", fromlist=["ScheduleConfig"]).ScheduleConfig(),
        ai=__import__("email_analyzer.config", fromlist=["AIConfig"]).AIConfig(),
        gmail=__import__("email_analyzer.config", fromlist=["GmailConfig"]).GmailConfig(),
        paths=__import__("email_analyzer.config", fromlist=["PathsConfig"]).PathsConfig(),
        slack=__import__("email_analyzer.config", fromlist=["SlackConfig"]).SlackConfig(),
        sender_rules=rules,
    )


def _msg(
    from_email: str,
    *,
    from_addr: str = "",
    subject: str = "Test",
    category: str | None = None,
    labels: list[str] | None = None,
    list_id: str = "",
    list_unsubscribe: str = "",
    precedence: str = "",
) -> EmailMessage:
    return EmailMessage(
        message_id="1",
        thread_id="t",
        internal_date_ms=0,
        from_addr=from_addr or from_email,
        from_email=from_email,
        subject=subject,
        date_header="",
        snippet="",
        category=category,
        labels=labels or [],
        list_id=list_id,
        list_unsubscribe=list_unsubscribe,
        precedence=precedence,
    )


def test_alphasignal_is_newsletter():
    rules = SenderRules(
        newsletter_patterns=[NewsletterPattern(from_contains="alphasignal")],
        newsletter_domains=["tldrnewsletter.com"],
        community_domains=["lists.boost.org"],
    )
    config = _config(rules)
    msg = _msg(
        "news@alphasignal.ai",
        from_addr="AlphaSignal <news@alphasignal.ai>",
        subject="Cognition's FrontierCode benchmark",
    )
    assert classify_by_rules(config, msg) == "newsletter"


def test_alphasignal_without_tldr_subject_is_newsletter():
    """AlphaSignal subjects are not TLDR-prefixed; from_contains alone must match."""
    rules = SenderRules(
        newsletter_patterns=[NewsletterPattern(from_contains="alphasignal")],
        newsletter_domains=["tldrnewsletter.com"],
    )
    config = _config(rules)
    msg = _msg(
        "news@alphasignal.ai",
        from_addr="AlphaSignal <news@alphasignal.ai>",
        subject="Claude Fable 5 leaked prompts reveal new Mythos tier",
    )
    assert classify_by_rules(config, msg) == "newsletter"


def test_tldr_domain_is_newsletter():
    rules = SenderRules(
        newsletter_patterns=[NewsletterPattern(from_contains="alphasignal")],
        newsletter_domains=["tldrnewsletter.com"],
    )
    config = _config(rules)
    msg = _msg(
        "dan@tldrnewsletter.com",
        from_addr="TLDR AI <dan@tldrnewsletter.com>",
        subject="Claude Fable 5",
    )
    assert classify_by_rules(config, msg) == "newsletter"


def test_lists_boost_org_is_community():
    rules = SenderRules(
        newsletter_domains=["tldrnewsletter.com"],
        community_domains=["lists.boost.org"],
    )
    config = _config(rules)
    msg = _msg(
        "boost@lists.boost.org",
        from_addr="Christian Mazakas via Boost <boost@lists.boost.org>",
        subject="[boost] Re: Boost.Graph Documentation",
    )
    assert classify_by_rules(config, msg) == "community"


def test_stale_category_is_reclassified():
    rules = SenderRules(
        newsletter_domains=["tldrnewsletter.com"],
        community_domains=["lists.boost.org"],
    )
    config = _config(rules)
    msg = _msg(
        "dan@tldrnewsletter.com",
        from_addr="TLDR <dan@tldrnewsletter.com>",
        subject="Daily digest",
        category="other",
    )
    assert classify_message(config, msg) == "newsletter"


def test_unknown_sender_is_other():
    rules = SenderRules(
        newsletter_domains=["tldrnewsletter.com"],
        community_domains=["lists.boost.org"],
    )
    config = _config(rules)
    msg = _msg("person@example.com", subject="Hello")
    assert classify_message(config, msg) == "other"


def test_list_unsubscribe_is_newsletter():
    config = _config(SenderRules())
    msg = _msg(
        "digest@unknown.example",
        list_unsubscribe="<mailto:unsub@unknown.example>",
    )
    assert classify_by_rules(config, msg) is None
    assert classify_message(config, msg) == "newsletter"


def test_precedence_list_is_newsletter():
    config = _config(SenderRules())
    msg = _msg("digest@unknown.example", precedence="list")
    assert classify_message(config, msg) == "newsletter"


def test_category_forums_is_community():
    config = _config(SenderRules())
    msg = _msg("user@forum.example", labels=["INBOX", "CATEGORY_FORUMS"])
    assert classify_message(config, msg) == "community"


def test_list_id_boost_token_is_community():
    config = _config(SenderRules())
    msg = _msg(
        "poster@example.com",
        list_id="<boost@lists.boost.org>",
    )
    assert classify_message(config, msg) == "community"


def test_yaml_wins_over_forum_heuristic():
    rules = SenderRules(newsletter_domains=["tldrnewsletter.com"])
    config = _config(rules)
    msg = _msg(
        "dan@tldrnewsletter.com",
        labels=["CATEGORY_FORUMS"],
        list_unsubscribe="<mailto:unsub@tldrnewsletter.com>",
    )
    assert classify_message(config, msg) == "newsletter"


def test_stale_archive_without_list_headers_is_other():
    config = _config(SenderRules())
    msg = _msg("person@example.com", subject="Hello")
    assert msg.list_id == ""
    assert msg.list_unsubscribe == ""
    assert msg.precedence == ""
    assert classify_message(config, msg) == "other"


def test_group_messages_by_category():
    grouped = group_messages_by_category(
        [
            _msg("a@example.com", category="newsletter"),
            _msg("b@example.com", category="community"),
            _msg("c@example.com", category=None),
        ]
    )
    assert len(grouped["newsletter"]) == 1
    assert len(grouped["community"]) == 1
    assert len(grouped["other"]) == 1
