"""Adapter for Claude Code CLI and Cursor CLI."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from email_analyzer.config import AppConfig
from email_analyzer.storage.paths import prompts_dir

_SUBPROCESS_ENCODING = "utf-8"


def _normalize_output(value: str | None) -> str:
    return value if value is not None else ""


def _run_subprocess(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """Run subprocess with UTF-8 stdout/stderr (Windows defaults to cp1252)."""
    env = kwargs.pop("env", None)
    if env is not None:
        env = {**env, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=_SUBPROCESS_ENCODING,
        errors="replace",
        env=env,
        **kwargs,
    )


def claude_subprocess_env(config: AppConfig) -> dict[str, str]:
    """Build environment for Claude Code CLI, optionally routing via OpenRouter."""
    env = os.environ.copy()
    or_cfg = config.ai.openrouter
    if not or_cfg.enabled:
        return env

    api_key = or_cfg.api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OpenRouter is enabled but OPENROUTER_API_KEY is not set. Add it to .env"
        )

    env["ANTHROPIC_BASE_URL"] = or_cfg.base_url
    env["ANTHROPIC_AUTH_TOKEN"] = api_key
    env["ANTHROPIC_API_KEY"] = ""
    if or_cfg.disable_nonessential_traffic:
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    sonnet = or_cfg.default_sonnet_model or or_cfg.model
    opus = or_cfg.default_opus_model or or_cfg.model
    haiku = or_cfg.default_haiku_model or or_cfg.model
    if sonnet:
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = sonnet
    if opus:
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = opus
    if haiku:
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = haiku
    return env


def run_prompt(
    config: AppConfig,
    user_input: str,
    *,
    system_prompt: str | None = None,
    system_prompt_file: Path | None = None,
    mode: str = "report",
) -> tuple[str, str, int]:
    """
    Run configured AI CLI and return (stdout, stderr, exit_code).

    mode: report | classify | weekly | monthly
    """
    provider = config.ai.provider.lower()
    timeout = config.ai.timeout_seconds

    if provider == "claude":
        return _run_claude(config, user_input, system_prompt, system_prompt_file, timeout)
    if provider == "cursor":
        return _run_cursor(config, user_input, system_prompt, system_prompt_file, timeout, mode)
    raise ValueError(f"Unknown AI provider: {provider}")


def _run_claude(
    config: AppConfig,
    user_input: str,
    system_prompt: str | None,
    system_prompt_file: Path | None,
    timeout: int,
) -> tuple[str, str, int]:
    cmd = [
        config.ai.claude_bin,
        "-p",
        "--bare",
        "--tools",
        "",
        "--output-format",
        "text",
    ]
    if system_prompt_file and system_prompt_file.exists():
        cmd.extend(["--system-prompt-file", str(system_prompt_file)])
    elif system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(user_input)
        input_path = f.name

    try:
        with open(input_path, encoding="utf-8") as stdin_file:
            proc = _run_subprocess(
                cmd,
                stdin=stdin_file,
                timeout=timeout,
                cwd=str(config.root),
                env=claude_subprocess_env(config),
            )
        return (
            _normalize_output(proc.stdout),
            _normalize_output(proc.stderr),
            proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return "", "AI CLI timed out", 1
    except FileNotFoundError:
        return "", f"CLI not found: {config.ai.claude_bin}", 127
    finally:
        Path(input_path).unlink(missing_ok=True)


def _run_cursor(
    config: AppConfig,
    user_input: str,
    system_prompt: str | None,
    system_prompt_file: Path | None,
    timeout: int,
    mode: str,
) -> tuple[str, str, int]:
    prompt_parts: list[str] = []
    if system_prompt_file and system_prompt_file.exists():
        prompt_parts.append(system_prompt_file.read_text(encoding="utf-8"))
    elif system_prompt:
        prompt_parts.append(system_prompt)
    prompt_parts.append(user_input)
    full_prompt = "\n\n".join(prompt_parts)

    cmd = [
        config.ai.cursor_bin,
        "-p",
        "--mode",
        "ask",
        "--output-format",
        "text",
        full_prompt,
    ]

    try:
        proc = _run_subprocess(
            cmd,
            timeout=timeout,
            cwd=str(config.root),
        )
        return (
            _normalize_output(proc.stdout),
            _normalize_output(proc.stderr),
            proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return "", "AI CLI timed out", 1
    except FileNotFoundError:
        return "", f"CLI not found: {config.ai.cursor_bin}", 127


def prompt_file_for_mode(config: AppConfig, mode: str) -> Path:
    mapping = {
        "report": "daily_report.md",
        "daily": "daily_report.md",
        "weekly": "weekly_report.md",
        "monthly": "monthly_report.md",
    }
    name = mapping.get(mode, "daily_report.md")
    return prompts_dir(config) / name
