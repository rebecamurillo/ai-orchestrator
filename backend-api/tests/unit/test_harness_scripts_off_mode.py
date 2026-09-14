"""Off-mode integration tests for the three harness configure scripts.

AC 1: unset env → non-zero exit naming one of the four guard variables.
AC 2: LITELLM_BASE_URL="" (gateway off), Langfuse set → exit 0; no gateway route; OTLP present.
AC 3: LANGFUSE_BASE_URL="" (tracing off), gateway set → exit 0; no OTEL entries; gateway route
    present.
AC 4: both blank → exit 0; every file parses; no gateway route or tracing config; mode 600.
AC 5: .env.example values (both on) → all expected keys/sections present.
AC 6: LITELLM_BASE_URL="" → doctor_gateway exits 0 and stderr contains "gateway disabled".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
MODE_600 = 0o600
HARNESSES = ("claude", "codex", "opencode")

REQUIRED_AT_CONFIGURE = (
    "LITELLM_BASE_URL",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


# ── helpers ──────────────────────────────────────────────────────────────────


def _base_env(tmp_path: Path) -> dict[str, str]:
    """Full .env.example values with AGENT_HOME pointing to a temp dir."""
    base = parse_env_example(ENV_EXAMPLE)
    return {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", str(tmp_path)),
        **base,
        "AGENT_HOME": str(tmp_path),  # overrides .env.example's /home/agent
    }


def run_configure(
    name: str,
    overrides: dict[str, str],
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    env = {**_base_env(tmp_path), **overrides}
    return subprocess.run(
        ["bash", str(HARNESS_DIR / f"{name}.sh"), "configure"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def read_claude(tmp_path: Path) -> dict:
    return json.loads((tmp_path / ".claude" / "settings.json").read_text())


def read_codex(tmp_path: Path) -> dict:
    return tomllib.loads((tmp_path / ".codex" / "config.toml").read_text())


def read_opencode(tmp_path: Path) -> dict:
    return json.loads((tmp_path / ".config" / "opencode" / "opencode.json").read_text())


# ── AC 1: unset env refuses ───────────────────────────────────────────────────


@pytest.mark.parametrize("name", HARNESSES)
def test_ac1_configure_refuses_with_nothing_configured(name: str, tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(HARNESS_DIR / f"{name}.sh"), "configure"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", str(tmp_path))},
    )
    assert result.returncode != 0
    assert any(v in result.stderr for v in REQUIRED_AT_CONFIGURE), result.stderr


# ── AC 2: gateway off, tracing on ────────────────────────────────────────────


def test_ac2_gateway_off_claude_exits_zero(tmp_path: Path) -> None:
    result = run_configure("claude", {"LITELLM_BASE_URL": ""}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "gateway disabled" in result.stderr


def test_ac2_gateway_off_claude_no_anthropic_base_url(tmp_path: Path) -> None:
    run_configure("claude", {"LITELLM_BASE_URL": ""}, tmp_path)
    env = read_claude(tmp_path)["env"]
    assert "ANTHROPIC_BASE_URL" not in env


def test_ac2_gateway_off_claude_has_otel(tmp_path: Path) -> None:
    run_configure("claude", {"LITELLM_BASE_URL": ""}, tmp_path)
    env = read_claude(tmp_path)["env"]
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in env


def test_ac2_gateway_off_codex_exits_zero(tmp_path: Path) -> None:
    result = run_configure("codex", {"LITELLM_BASE_URL": ""}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "gateway disabled" in result.stderr


def test_ac2_gateway_off_codex_no_model_provider(tmp_path: Path) -> None:
    run_configure("codex", {"LITELLM_BASE_URL": ""}, tmp_path)
    cfg = read_codex(tmp_path)
    assert "model_provider" not in cfg
    assert "model_providers" not in cfg


def test_ac2_gateway_off_codex_has_otel(tmp_path: Path) -> None:
    run_configure("codex", {"LITELLM_BASE_URL": ""}, tmp_path)
    cfg = read_codex(tmp_path)
    assert "otel" in cfg


def test_ac2_gateway_off_opencode_exits_zero(tmp_path: Path) -> None:
    result = run_configure("opencode", {"LITELLM_BASE_URL": ""}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "gateway disabled" in result.stderr


def test_ac2_gateway_off_opencode_no_provider(tmp_path: Path) -> None:
    run_configure("opencode", {"LITELLM_BASE_URL": ""}, tmp_path)
    cfg = read_opencode(tmp_path)
    assert "provider" not in cfg


def test_ac2_gateway_off_opencode_has_plugin_and_experimental(tmp_path: Path) -> None:
    run_configure("opencode", {"LITELLM_BASE_URL": ""}, tmp_path)
    cfg = read_opencode(tmp_path)
    assert "plugin" in cfg
    assert "experimental" in cfg


# ── AC 3: tracing off, gateway on ────────────────────────────────────────────


def test_ac3_tracing_off_claude_exits_zero(tmp_path: Path) -> None:
    result = run_configure("claude", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "tracing disabled" in result.stderr


def test_ac3_tracing_off_claude_no_otlp(tmp_path: Path) -> None:
    run_configure("claude", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    env = read_claude(tmp_path)["env"]
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in env


def test_ac3_tracing_off_claude_has_gateway(tmp_path: Path) -> None:
    run_configure("claude", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    env = read_claude(tmp_path)["env"]
    assert "ANTHROPIC_BASE_URL" in env


def test_ac3_tracing_off_codex_exits_zero(tmp_path: Path) -> None:
    result = run_configure("codex", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "tracing disabled" in result.stderr


def test_ac3_tracing_off_codex_no_otel(tmp_path: Path) -> None:
    run_configure("codex", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    cfg = read_codex(tmp_path)
    assert "otel" not in cfg


def test_ac3_tracing_off_codex_has_model_provider(tmp_path: Path) -> None:
    run_configure("codex", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    cfg = read_codex(tmp_path)
    assert "model_provider" in cfg
    assert "model_providers" in cfg


def test_ac3_tracing_off_opencode_exits_zero(tmp_path: Path) -> None:
    result = run_configure("opencode", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "tracing disabled" in result.stderr


def test_ac3_tracing_off_opencode_no_plugin_or_experimental(tmp_path: Path) -> None:
    run_configure("opencode", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    cfg = read_opencode(tmp_path)
    assert "plugin" not in cfg
    assert "experimental" not in cfg


def test_ac3_tracing_off_opencode_has_provider(tmp_path: Path) -> None:
    run_configure("opencode", {"LANGFUSE_BASE_URL": ""}, tmp_path)
    cfg = read_opencode(tmp_path)
    assert "provider" in cfg


# ── AC 4: both off ────────────────────────────────────────────────────────────

_BOTH_OFF = {"LITELLM_BASE_URL": "", "LANGFUSE_BASE_URL": ""}


@pytest.mark.parametrize("name", HARNESSES)
def test_ac4_both_off_exits_zero(name: str, tmp_path: Path) -> None:
    result = run_configure(name, _BOTH_OFF, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "gateway disabled" in result.stderr
    assert "tracing disabled" in result.stderr


def test_ac4_both_off_claude_parses_no_gateway_no_tracing(tmp_path: Path) -> None:
    run_configure("claude", _BOTH_OFF, tmp_path)
    env = read_claude(tmp_path)["env"]
    assert "ANTHROPIC_BASE_URL" not in env
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in env


def test_ac4_both_off_codex_parses_no_gateway_no_tracing(tmp_path: Path) -> None:
    run_configure("codex", _BOTH_OFF, tmp_path)
    cfg = read_codex(tmp_path)
    assert "model_provider" not in cfg
    assert "model_providers" not in cfg
    assert "otel" not in cfg


def test_ac4_both_off_opencode_parses_no_gateway_no_tracing(tmp_path: Path) -> None:
    run_configure("opencode", _BOTH_OFF, tmp_path)
    cfg = read_opencode(tmp_path)
    assert "provider" not in cfg
    assert "plugin" not in cfg
    assert "experimental" not in cfg


def test_ac4_both_off_mode_600(tmp_path: Path) -> None:
    for name in HARNESSES:
        run_configure(name, _BOTH_OFF, tmp_path)
    files = [
        tmp_path / ".claude" / "settings.json",
        tmp_path / ".codex" / "config.toml",
        tmp_path / ".config" / "opencode" / "opencode.json",
    ]
    for f in files:
        assert f.exists(), f"{f} was not written"
        assert f.stat().st_mode & 0o777 == MODE_600, f"{f} is not mode 600"


# ── AC 5: both on (.env.example values) ──────────────────────────────────────


def test_ac5_both_on_claude(tmp_path: Path) -> None:
    result = run_configure("claude", {}, tmp_path)
    assert result.returncode == 0, result.stderr
    env = read_claude(tmp_path)["env"]
    assert "ANTHROPIC_BASE_URL" in env
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in env
    assert "DISABLE_AUTOUPDATER" in env


def test_ac5_both_on_codex(tmp_path: Path) -> None:
    result = run_configure("codex", {}, tmp_path)
    assert result.returncode == 0, result.stderr
    cfg = read_codex(tmp_path)
    assert "model_provider" in cfg
    assert "model_providers" in cfg
    assert "otel" in cfg


def test_ac5_both_on_opencode(tmp_path: Path) -> None:
    result = run_configure("opencode", {}, tmp_path)
    assert result.returncode == 0, result.stderr
    cfg = read_opencode(tmp_path)
    assert "provider" in cfg
    assert "plugin" in cfg
    assert "experimental" in cfg
    assert "permission" in cfg


# ── AC 6: doctor_gateway disabled ────────────────────────────────────────────


def test_ac6_doctor_gateway_disabled_exits_zero_no_network(tmp_path: Path) -> None:
    common_path = HARNESS_DIR / "_common.sh"
    wrapper = tmp_path / "test_doctor_gateway.sh"
    wrapper.write_text(f'#!/usr/bin/env bash\nsource "{common_path}"\ndoctor_gateway\n')
    wrapper.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "LITELLM_BASE_URL": "",  # declared-blank = gateway off
        },
    )
    assert result.returncode == 0, result.stderr
    assert "gateway disabled" in result.stderr
