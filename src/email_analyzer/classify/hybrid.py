"""Backward-compatible re-export of the rule-based classifier."""

from email_analyzer.classify.rules import (
    CATEGORIES,
    Category,
    classify_by_rules,
    classify_message,
    classify_messages,
    group_messages_by_category,
    reclassify_archived,
)

__all__ = [
    "CATEGORIES",
    "Category",
    "classify_by_rules",
    "classify_message",
    "classify_messages",
    "group_messages_by_category",
    "reclassify_archived",
]
