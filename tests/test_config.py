from pathlib import Path

import yaml

from email_analyzer.config import _deep_merge, _merged_yaml, load_config


def test_deep_merge_nested():
    base = {"ai": {"provider": "claude", "timeout_seconds": 300}, "gmail": {"broad_query": "in:inbox"}}
    override = {"ai": {"provider": "cursor"}}
    assert _deep_merge(base, override) == {
        "ai": {"provider": "cursor", "timeout_seconds": 300},
        "gmail": {"broad_query": "in:inbox"},
    }


def test_merged_yaml_uses_local_override(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.dump({"ai": {"provider": "claude"}, "schedule": {"run_hour": 18}}),
        encoding="utf-8",
    )
    (config_dir / "config.local.yaml").write_text(
        yaml.dump({"ai": {"provider": "cursor"}}),
        encoding="utf-8",
    )
    (config_dir / "sender_rules.yaml").write_text("newsletter: {}\ncommunity: {}", encoding="utf-8")

    merged = _merged_yaml(tmp_path, "config.yaml")
    assert merged["ai"]["provider"] == "cursor"
    assert merged["schedule"]["run_hour"] == 18


def test_merged_yaml_env_override(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.dump({"ai": {"provider": "claude"}}),
        encoding="utf-8",
    )
    personal = tmp_path / "personal.yaml"
    personal.write_text(yaml.dump({"ai": {"provider": "cursor"}}), encoding="utf-8")
    monkeypatch.setenv("MAIL_DIGEST_CONFIG", str(personal))

    merged = _merged_yaml(tmp_path, "config.yaml", env_var="MAIL_DIGEST_CONFIG")
    assert merged["ai"]["provider"] == "cursor"


def test_load_config_from_local_override(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "schedule": {"run_hour": 18, "run_minute": 0, "window_hours": 24},
                "ai": {"provider": "claude"},
                "gmail": {"broad_query": "in:inbox"},
                "paths": {},
                "slack": {},
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "config.local.yaml").write_text(
        yaml.dump({"ai": {"provider": "cursor"}}),
        encoding="utf-8",
    )
    (config_dir / "sender_rules.yaml").write_text(
        yaml.dump({"newsletter": {"patterns": [], "domains": [], "addresses": []}, "community": {}}),
        encoding="utf-8",
    )

    config = load_config(tmp_path)
    assert config.ai.provider == "cursor"
    assert config.schedule.run_hour == 18
