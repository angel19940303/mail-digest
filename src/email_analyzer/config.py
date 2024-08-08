"""Load configuration from YAML and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


def project_root() -> Path:
    env_root = os.environ.get("EMAIL_ANALYZER_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # Walk up from this file to find config/config.yaml
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "config" / "config.yaml").exists():
            return candidate
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd().resolve()


@dataclass
class ScheduleConfig:
    run_hour: int = 18
    run_minute: int = 0
    window_hours: int = 24


@dataclass
class OpenRouterConfig:
    enabled: bool = False
    base_url: str = "https://openrouter.ai/api"
    disable_nonessential_traffic: bool = True
    model: str = ""
    default_sonnet_model: str = ""
    default_opus_model: str = ""
    default_haiku_model: str = ""
    api_key: str | None = None


@dataclass
class AIConfig:
    provider: str = "claude"
    claude_bin: str = "claude"
    cursor_bin: str = "agent"
    timeout_seconds: int = 300
    max_body_chars_per_email: int = 4000
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)


@dataclass
class GmailConfig:
    credentials_file: str = "credentials.json"
    token_file: str = "token.json"
    scopes: list[str] = field(
        default_factory=lambda: ["https://www.googleapis.com/auth/gmail.readonly"]
    )
    broad_query: str = "in:inbox newer_than:2d"


@dataclass
class PathsConfig:
    emails: str = "emails"
    daily_reports: str = "daily_reports"
    weekly_reports: str = "weekly_reports"
    monthly_reports: str = "monthly_report"


@dataclass
class SlackConfig:
    max_bullets_per_section: int = 5
    max_chars_per_block: int = 2900


@dataclass
class NewsletterPattern:
    from_contains: str
    subject_prefix: str = ""


@dataclass
class SenderRules:
    newsletter_patterns: list[NewsletterPattern] = field(default_factory=list)
    newsletter_domains: list[str] = field(default_factory=list)
    newsletter_addresses: list[str] = field(default_factory=list)
    community_domains: list[str] = field(default_factory=list)
    community_addresses: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    root: Path
    schedule: ScheduleConfig
    ai: AIConfig
    gmail: GmailConfig
    paths: PathsConfig
    slack: SlackConfig
    sender_rules: SenderRules
    slack_webhook_url: str | None = None

    def resolve(self, relative: str) -> Path:
        return self.root / relative

    @property
    def credentials_path(self) -> Path:
        return self.resolve(self.gmail.credentials_file)

    @property
    def token_path(self) -> Path:
        return self.resolve(self.gmail.token_file)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(root: Path | str | None = None) -> AppConfig:
    load_dotenv()
    if root is None:
        root = project_root()
    elif isinstance(root, str):
        root = Path(root).resolve()

    raw = _load_yaml(root / "config" / "config.yaml")
    schedule_raw = raw.get("schedule", {})
    ai_raw = raw.get("ai", {})
    openrouter_raw = ai_raw.get("openrouter", {})
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    openrouter_enabled = bool(openrouter_raw.get("enabled", False)) or bool(openrouter_key)
    gmail_raw = raw.get("gmail", {})
    paths_raw = raw.get("paths", {})
    slack_raw = raw.get("slack", {})

    rules_raw = _load_yaml(root / "config" / "sender_rules.yaml")
    newsletter = rules_raw.get("newsletter", {})
    community = rules_raw.get("community", {})

    return AppConfig(
        root=root,
        schedule=ScheduleConfig(
            run_hour=int(schedule_raw.get("run_hour", 18)),
            run_minute=int(schedule_raw.get("run_minute", 0)),
            window_hours=int(schedule_raw.get("window_hours", 24)),
        ),
        ai=AIConfig(
            provider=str(ai_raw.get("provider", "claude")),
            claude_bin=str(ai_raw.get("claude_bin", "claude")),
            cursor_bin=str(ai_raw.get("cursor_bin", "agent")),
            timeout_seconds=int(ai_raw.get("timeout_seconds", 300)),
            max_body_chars_per_email=int(ai_raw.get("max_body_chars_per_email", 4000)),
            openrouter=OpenRouterConfig(
                enabled=openrouter_enabled,
                base_url=str(openrouter_raw.get("base_url", "https://openrouter.ai/api")),
                disable_nonessential_traffic=bool(
                    openrouter_raw.get("disable_nonessential_traffic", True)
                ),
                default_sonnet_model=str(openrouter_raw.get("default_sonnet_model", "")),
                default_opus_model=str(openrouter_raw.get("default_opus_model", "")),
                default_haiku_model=str(openrouter_raw.get("default_haiku_model", "")),
                model=str(openrouter_raw.get("model", "")),
                api_key=openrouter_key,
            ),
        ),
        gmail=GmailConfig(
            credentials_file=str(gmail_raw.get("credentials_file", "credentials.json")),
            token_file=str(gmail_raw.get("token_file", "token.json")),
            scopes=list(
                gmail_raw.get(
                    "scopes",
                    ["https://www.googleapis.com/auth/gmail.readonly"],
                )
            ),
            broad_query=str(gmail_raw.get("broad_query", "in:inbox newer_than:2d")),
        ),
        paths=PathsConfig(
            emails=str(paths_raw.get("emails", "emails")),
            daily_reports=str(paths_raw.get("daily_reports", "daily_reports")),
            weekly_reports=str(paths_raw.get("weekly_reports", "weekly_reports")),
            monthly_reports=str(paths_raw.get("monthly_reports", "monthly_report")),
        ),
        slack=SlackConfig(
            max_bullets_per_section=int(slack_raw.get("max_bullets_per_section", 5)),
            max_chars_per_block=int(slack_raw.get("max_chars_per_block", 2900)),
        ),
        sender_rules=SenderRules(
            newsletter_patterns=[
                NewsletterPattern(
                    from_contains=str(p.get("from_contains", "")).lower(),
                    subject_prefix=str(p.get("subject_prefix", "")),
                )
                for p in newsletter.get("patterns", [])
                if p.get("from_contains")
            ],
            newsletter_domains=[d.lower() for d in newsletter.get("domains", [])],
            newsletter_addresses=[a.lower() for a in newsletter.get("addresses", [])],
            community_domains=[d.lower() for d in community.get("domains", [])],
            community_addresses=[a.lower() for a in community.get("addresses", [])],
        ),
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"),
    )
