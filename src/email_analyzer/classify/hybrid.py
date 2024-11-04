"""Rule-based email classification."""

from __future__ import annotations

from typing import Literal

from email_analyzer.config import AppConfig, NewsletterPattern
from email_analyzer.gmail.fetch import EmailMessage
from email_analyzer.storage.emails import update_message_category

Category = Literal["newsletter", "community", "other"]


def _domain_matches(email_addr: str, domains: list[str]) -> bool:
    if not email_addr or "@" not in email_addr:
        return False
    domain = email_addr.split("@", 1)[1].lower()
    return domain in [d.lower() for d in domains]


def _matches_newsletter_pattern(msg: EmailMessage, pattern: NewsletterPattern) -> bool:
    from_text = f"{msg.from_addr} {msg.from_email}".lower()
    if pattern.from_contains not in from_text:
        return False
    if pattern.subject_prefix:
        return msg.subject.strip().upper().startswith(pattern.subject_prefix.upper())
    return True


def classify_by_rules(config: AppConfig, msg: EmailMessage) -> Category | None:
    rules = config.sender_rules

    for pattern in rules.newsletter_patterns:
        if _matches_newsletter_pattern(msg, pattern):
            return "newsletter"

    addr = msg.from_email.lower()
    if addr in rules.newsletter_addresses or _domain_matches(addr, rules.newsletter_domains):
        return "newsletter"
    if addr in rules.community_addresses or _domain_matches(addr, rules.community_domains):
        return "community"
    return None


def classify_message(config: AppConfig, msg: EmailMessage) -> Category:
    # Always apply rules (do not trust stale category from a prior run).
    return classify_by_rules(config, msg) or "other"


def classify_messages(
    config: AppConfig,
    messages: list[EmailMessage],
    report_date,
) -> list[EmailMessage]:
    classified: list[EmailMessage] = []
    for msg in messages:
        cat = classify_message(config, msg)
        msg.category = cat
        update_message_category(config, report_date, msg.message_id, cat)
        classified.append(msg)
    return classified
