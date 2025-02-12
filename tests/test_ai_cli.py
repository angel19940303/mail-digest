from email_analyzer.config import AIConfig, AppConfig, OpenRouterConfig, PathsConfig, ScheduleConfig, SenderRules, SlackConfig, GmailConfig
from email_analyzer.reports.ai_cli import claude_subprocess_env


def _config(openrouter: OpenRouterConfig) -> AppConfig:
    return AppConfig(
        root=__import__("pathlib").Path("."),
        schedule=ScheduleConfig(),
        ai=AIConfig(openrouter=openrouter),
        gmail=GmailConfig(),
        paths=PathsConfig(),
        slack=SlackConfig(),
        sender_rules=SenderRules(),
    )


def test_openrouter_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-cleared")

    config = _config(
        OpenRouterConfig(
            enabled=True,
            api_key="sk-or-v1-test",
            default_sonnet_model="anthropic/claude-sonnet-4",
        )
    )
    env = claude_subprocess_env(config)

    assert env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-or-v1-test"
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "anthropic/claude-sonnet-4"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"


def test_openrouter_model_shorthand(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    config = _config(
        OpenRouterConfig(
            enabled=True,
            api_key="sk-or-v1-test",
            model="openai/gpt-4o-mini",
        )
    )
    env = claude_subprocess_env(config)
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "openai/gpt-4o-mini"
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "openai/gpt-4o-mini"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "openai/gpt-4o-mini"


def test_normalize_output_handles_none():
    from email_analyzer.reports.ai_cli import _normalize_output

    assert _normalize_output(None) == ""
    assert _normalize_output("hello") == "hello"


def test_openrouter_disabled_passthrough(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "native-key")
    config = _config(OpenRouterConfig(enabled=False))
    env = claude_subprocess_env(config)
    assert env["ANTHROPIC_API_KEY"] == "native-key"
