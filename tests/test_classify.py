from email_analyzer.classify.hybrid import classify_by_rules, classify_message
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
