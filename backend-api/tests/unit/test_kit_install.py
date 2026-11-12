"""`deploy/kit/install.sh` — the bootstrap installer.

Rewritten under the declared behaviour change AD-33 (owner, 2026-11-11; epic 3 story 2): the
installer renders one `orchestrator` bootstrap skill, configures the agent connection (MCP) per
harness, writes `.orchestrator/bootstrap.json`, and never takes or writes a token value. The
four-skill kit, `bin/`, `.env` and `kit.json` behaviour it replaces is no longer pinned.

No Docker and no network: a `curl` shim on PATH answers the version probe and the archive.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

KIT_DIR = REPO_ROOT / "deploy" / "kit"
INSTALL = KIT_DIR / "install.sh"

BASE = "https://orchestrator.example"
WEB = "https://web.example"
SECRET = "tok-secret-value"
RELEASE = re.compile(r"\b\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?\b")

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

CURL_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_LOG"
out=""
url=""
wants_code=0
prev=""
for arg in "$@"; do
\tif [ "$prev" = "-o" ]; then out="$arg"; fi
\tif [ "$arg" = "-w" ]; then wants_code=1; fi
\tcase "$arg" in http*) url="$arg" ;; esac
\tprev="$arg"
done
emit() {
\tif [ -n "$out" ]; then if [ -n "$2" ]; then cp "$2" "$out"; else : > "$out"; fi; fi
\tif [ "$wants_code" = 1 ]; then printf '%s' "$1"; exit 0; fi
\tcase "$1" in 2??) exit 0 ;; esac
\texit 22
}
case "$url" in
\t*/api/v1/version) emit "${SHIM_VERSION_CODE:-200}" "${SHIM_VERSION_FILE:-}" ;;
\t*/api/v1/kit/archive) emit "${SHIM_ARCHIVE_CODE:-200}" "${SHIM_ARCHIVE:-}" ;;
esac
emit 404 ""
"""

OLD_SKILLS = ("orchestrator", "orchestrator-admin", "initiative-spec", "initiative-run")


class Env:
    """One scratch world: a project, a HOME, CODEX_HOME and XDG under `tmp_path`."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.project = tmp_path / "project"
        self.project.mkdir()
        self.home = tmp_path / "home"
        self.codex = tmp_path / "codex"
        self.xdg = tmp_path / "xdg"
        for d in (self.home, self.codex, self.xdg):
            d.mkdir()
        bin_dir = tmp_path / "shimbin"
        bin_dir.mkdir()
        (bin_dir / "curl").write_text(CURL_SHIM)
        (bin_dir / "curl").chmod(0o755)
        self.log = tmp_path / "curl.log"
        self.log.touch()
        self.extra: dict[str, str] = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SHIM_LOG": str(self.log),
        }

    def run(
        self,
        *args: str,
        script: Path = INSTALL,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        clean = {k: v for k, v in os.environ.items() if not k.startswith("ORCHESTRATOR_")}
        full = {
            **clean,
            **self.extra,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.codex),
            "XDG_CONFIG_HOME": str(self.xdg),
            **(env or {}),
        }
        return subprocess.run(  # fixed argv, no shell
            ["bash", str(script), *args],
            capture_output=True,
            text=True,
            cwd=cwd or self.project,
            env=full,
            check=False,
        )

    def install(
        self, harness: str = "claude", *extra: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self.run("--harness", harness, "--base-url", BASE, *extra, env=env)

    def written_files(self) -> list[Path]:
        files: list[Path] = []
        for d in (self.project, self.home, self.codex, self.xdg):
            files += [p for p in d.rglob("*") if p.is_file()]
        return files

    def piped_script(self) -> Path:
        piped = self.root / "piped"
        piped.mkdir()
        shutil.copy(INSTALL, piped / "install.sh")
        return piped / "install.sh"

    def version_body(self, release: str = "9.9.9", contract: int = 1) -> str:
        body = self.root / "version.json"
        body.write_text(json.dumps({"app_version": release, "bootstrap_contract": contract}))
        return str(body)

    def archive(self) -> str:
        path = self.root / "kit.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for entry in sorted(KIT_DIR.iterdir()):
                tar.add(entry, arcname=entry.name)
        return str(path)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def _ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


SKILL_CLAUDE = ".claude/skills/orchestrator/SKILL.md"
SKILL_AGENTS = ".agents/skills/orchestrator/SKILL.md"


# ── the script parses and refuses ────────────────────────────────────────────


@needs_bash
def test_the_script_parses_and_is_executable() -> None:
    assert INSTALL.stat().st_mode & 0o111
    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(INSTALL)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@needs_bash
def test_help_names_every_flag(env: Env) -> None:
    result = env.run("--help")

    _ok(result)
    for flag in ("--harness", "--base-url", "--web-url", "--token-var", "--project", "--home"):
        assert flag in result.stdout, flag
    for harness in ("claude", "codex", "opencode", "all"):
        assert harness in result.stdout, harness


@needs_bash
def test_an_unknown_harness_is_refused(env: Env) -> None:
    result = env.run("--harness", "cursor")

    assert result.returncode != 0
    assert "--harness" in result.stderr
    assert env.written_files() == []


@needs_bash
def test_a_bad_token_var_is_refused(env: Env) -> None:
    result = env.run("--token-var", "lower-case")

    assert result.returncode != 0
    assert "--token-var" in result.stderr
    assert env.written_files() == []


@needs_bash
def test_project_with_home_is_refused(env: Env) -> None:
    result = env.run("--project", str(env.project), "--home")

    assert result.returncode != 0
    assert env.written_files() == []


@needs_bash
@pytest.mark.parametrize("form", [["--token", "x"], ["--token=x"]])
def test_a_token_value_is_refused(env: Env, form: list[str]) -> None:
    result = env.run(*form)

    assert result.returncode != 0
    assert "pass the variable's name with --token-var" in result.stderr
    assert env.written_files() == []


# ── what each harness gets ───────────────────────────────────────────────────


def _check_claude_mcp(env: Env) -> None:
    cfg = json.loads((env.project / ".mcp.json").read_text())
    server = cfg["mcpServers"]["orchestrator"]
    assert server["url"] == f"{BASE}/mcp"
    assert server["headers"]["Authorization"] == "Bearer ${ORCHESTRATOR_TOKEN}"


def _check_codex_mcp(env: Env) -> None:
    cfg = tomllib.loads((env.codex / "config.toml").read_text())
    server = cfg["mcp_servers"]["orchestrator"]
    assert server["url"] == f"{BASE}/mcp"
    assert server["bearer_token_env_var"] == "ORCHESTRATOR_TOKEN"


def _check_opencode_mcp(env: Env) -> None:
    cfg = json.loads((env.project / "opencode.json").read_text())
    server = cfg["mcp"]["orchestrator"]
    assert server["url"] == f"{BASE}/mcp"
    assert server["headers"]["Authorization"] == "Bearer {env:ORCHESTRATOR_TOKEN}"


@needs_bash
@pytest.mark.parametrize("harness", ["claude", "codex", "opencode", "all"])
def test_each_harness_gets_its_bootstrap_and_connection(env: Env, harness: str) -> None:
    result = env.install(harness, "--web-url", WEB, env={"ORCHESTRATOR_TOKEN": SECRET})

    _ok(result)
    claude = harness in ("claude", "all")
    agents = harness in ("codex", "opencode", "all")
    assert (env.project / SKILL_CLAUDE).is_file() is claude
    assert (env.project / SKILL_AGENTS).is_file() is agents
    if claude:
        _check_claude_mcp(env)
    if harness in ("codex", "all"):
        _check_codex_mcp(env)
        assert "per-user" in result.stdout
    if harness in ("opencode", "all"):
        _check_opencode_mcp(env)
    bootstrap = json.loads((env.project / ".orchestrator" / "bootstrap.json").read_text())
    assert bootstrap["harness"] == harness


@needs_bash
def test_claude_leaves_exactly_three_files_and_no_secret_or_release(env: Env) -> None:
    result = env.install(
        "claude", "--web-url", WEB, env={"ORCHESTRATOR_TOKEN": SECRET, "SHIM_VERSION_FILE": ""}
    )

    _ok(result)
    rel = sorted(str(p.relative_to(env.project)) for p in env.project.rglob("*") if p.is_file())
    assert rel == sorted([".mcp.json", SKILL_CLAUDE, ".orchestrator/bootstrap.json"])
    assert [p for p in env.home.rglob("*") if p.is_file()] == []
    for path in env.written_files():
        text = path.read_text()
        assert SECRET not in text, path
        assert not RELEASE.search(text), (path, RELEASE.search(text))
    assert SECRET not in result.stdout + result.stderr


@needs_bash
@pytest.mark.parametrize("harness", ["codex", "opencode", "all"])
def test_no_written_file_holds_a_release_string_or_the_token(env: Env, harness: str) -> None:
    result = env.install(harness, env={"ORCHESTRATOR_TOKEN": SECRET})

    _ok(result)
    for path in env.written_files():
        text = path.read_text()
        assert SECRET not in text, path
        assert not RELEASE.search(text), (path, RELEASE.search(text))
    assert SECRET not in result.stdout + result.stderr


@needs_bash
def test_bootstrap_json_keys_and_no_credential(env: Env) -> None:
    _ok(env.install("claude", env={"ORCHESTRATOR_TOKEN": SECRET}))

    data = json.loads((env.project / ".orchestrator" / "bootstrap.json").read_text())

    assert set(data) == {"bootstrap_contract", "harness", "base_url", "installed_at"}
    assert data["bootstrap_contract"] == 1
    assert data["base_url"] == BASE
    assert data["installed_at"].endswith("Z")


# ── the rendered bootstrap ───────────────────────────────────────────────────


@needs_bash
def test_rendering_without_a_web_url(env: Env) -> None:
    _ok(env.install("claude"))

    text = (env.project / SKILL_CLAUDE).read_text()

    assert "No web address was given." in text
    assert "@@" not in text
    assert "bootstrap_contract: 1" in text
    assert "name: orchestrator" in text
    assert BASE in text
    assert (
        "The token is in the environment variable `ORCHESTRATOR_TOKEN`; "
        "never write its value into a file." in text
    )
    for rule in (
        "a Run's budget is the owner's decision, never invented or raised by the agent",
        "preflight comes before every launch",
        "answer a park only with what the Run offers",
        "a remote agent never maintains the installation",
    ):
        assert rule in text, rule
    assert "Call the `version` tool" in text
    assert "`read_guide` with no id" in text


@needs_bash
def test_rendering_with_a_web_url(env: Env) -> None:
    _ok(env.install("claude", "--web-url", WEB + "/"))

    text = (env.project / SKILL_CLAUDE).read_text()

    assert WEB in text
    assert WEB + "/" not in text
    assert "No web address was given." not in text


@needs_bash
def test_special_characters_in_a_value_survive_literally(env: Env) -> None:
    base = "https://o.example/a&b|c\\d"
    result = env.run("--harness", "claude", "--base-url", base)

    _ok(result)
    assert base in (env.project / SKILL_CLAUDE).read_text()


@needs_bash
def test_a_custom_token_var_is_referenced_by_name(env: Env) -> None:
    _ok(env.install("all", "--token-var", "MY_TOKEN"))

    assert "`MY_TOKEN`" in (env.project / SKILL_CLAUDE).read_text()
    assert "Bearer ${MY_TOKEN}" in (env.project / ".mcp.json").read_text()
    assert 'bearer_token_env_var = "MY_TOKEN"' in (env.codex / "config.toml").read_text()
    assert "Bearer {env:MY_TOKEN}" in (env.project / "opencode.json").read_text()


@needs_bash
def test_a_trailing_slash_is_stripped(env: Env) -> None:
    _ok(env.run("--harness", "claude", "--base-url", BASE + "/"))

    _check_claude_mcp(env)


@needs_bash
def test_re_running_replaces_the_skill_folder(env: Env) -> None:
    _ok(env.install("claude"))
    stale = env.project / ".claude/skills/orchestrator/stale.md"
    stale.write_text("old\n")

    _ok(env.install("claude"))

    assert not stale.exists()
    assert [p.name for p in stale.parent.iterdir()] == ["SKILL.md"]


# ── --home ───────────────────────────────────────────────────────────────────


@needs_bash
def test_home_writes_under_home_and_xdg(env: Env) -> None:
    result = env.run("--harness", "all", "--base-url", BASE, "--home", cwd=env.root)

    _ok(result)
    assert (env.home / SKILL_CLAUDE).is_file()
    assert (env.home / SKILL_AGENTS).is_file()
    assert (env.home / ".orchestrator" / "bootstrap.json").is_file()
    cfg = json.loads((env.home / ".claude.json").read_text())
    assert cfg["mcpServers"]["orchestrator"]["url"] == f"{BASE}/mcp"
    oc = json.loads((env.xdg / "opencode" / "opencode.json").read_text())
    assert oc["mcp"]["orchestrator"]["url"] == f"{BASE}/mcp"
    assert (env.codex / "config.toml").is_file()
    assert [p for p in env.project.rglob("*")] == []


# ── existing configuration ───────────────────────────────────────────────────


@needs_bash
def test_a_json_config_with_another_server_is_merged(env: Env) -> None:
    (env.project / ".mcp.json").write_text(
        json.dumps({"keep": 1, "mcpServers": {"other": {"url": "x"}}})
    )

    _ok(env.install("claude"))

    cfg = json.loads((env.project / ".mcp.json").read_text())
    assert cfg["keep"] == 1
    assert cfg["mcpServers"]["other"] == {"url": "x"}
    assert cfg["mcpServers"]["orchestrator"]["url"] == f"{BASE}/mcp"


@needs_bash
def test_an_existing_orchestrator_entry_is_kept_byte_for_byte(env: Env) -> None:
    original = json.dumps({"mcpServers": {"orchestrator": {"url": "https://old.example/mcp"}}})
    (env.project / ".mcp.json").write_text(original)

    result = env.install("claude")

    _ok(result)
    assert (env.project / ".mcp.json").read_text() == original
    assert "https://old.example/mcp" in result.stdout
    assert f"{BASE}/mcp" in result.stdout
    assert "by hand" in result.stdout


@needs_bash
def test_an_existing_orchestrator_entry_with_the_same_url_is_kept_quietly(env: Env) -> None:
    original = json.dumps({"mcpServers": {"orchestrator": {"url": f"{BASE}/mcp"}}})
    (env.project / ".mcp.json").write_text(original)

    result = env.install("claude")

    _ok(result)
    assert (env.project / ".mcp.json").read_text() == original
    assert "by hand" not in result.stdout


@needs_bash
def test_an_invalid_json_config_stops_with_exit_1_and_is_unchanged(env: Env) -> None:
    (env.project / ".mcp.json").write_text("{not json")

    result = env.install("claude")

    assert result.returncode == 1
    assert ".mcp.json" in result.stderr
    assert (env.project / ".mcp.json").read_text() == "{not json"
    assert not (env.project / ".claude").exists()


@needs_bash
def test_opencode_jsonc_gets_nothing_written_and_exit_1(env: Env) -> None:
    (env.project / "opencode.jsonc").write_text("{}")

    result = env.install("opencode")

    assert result.returncode == 1
    assert not (env.project / "opencode.json").exists()
    assert "opencode.jsonc" in result.stderr + result.stdout
    assert f"{BASE}/mcp" in result.stdout + result.stderr


@needs_bash
def test_a_codex_config_with_another_table_gets_the_table_appended(env: Env) -> None:
    (env.codex / "config.toml").write_text('[other]\nkey = "v"')

    result = env.install("codex")

    _ok(result)
    cfg = tomllib.loads((env.codex / "config.toml").read_text())
    assert cfg["other"] == {"key": "v"}
    assert cfg["mcp_servers"]["orchestrator"]["url"] == f"{BASE}/mcp"
    assert "per-user" in result.stdout


@needs_bash
def test_an_existing_codex_table_is_kept_and_a_difference_printed(env: Env) -> None:
    original = '[mcp_servers.orchestrator]\nurl = "https://old.example/mcp"\n'
    (env.codex / "config.toml").write_text(original)

    result = env.install("codex")

    _ok(result)
    assert (env.codex / "config.toml").read_text() == original
    assert "https://old.example/mcp" in result.stdout
    assert "by hand" in result.stdout
    assert "per-user" in result.stdout


@needs_bash
@pytest.mark.parametrize(
    "original",
    [
        '  [mcp_servers.orchestrator]\n  url = "https://old.example/mcp"\n',
        '[mcp_servers."orchestrator"]\nurl = "https://old.example/mcp"\n',
        '[ mcp_servers.orchestrator ]\nurl = "https://old.example/mcp"\n',
        '[mcp_servers]\norchestrator = { url = "https://old.example/mcp" }\n',
        'mcp_servers.orchestrator.url = "https://old.example/mcp"\n',
        '[mcp_servers.orchestrator]\r\nurl = "https://old.example/mcp"\r\n',
    ],
)
def test_every_toml_spelling_of_the_codex_entry_is_kept(env: Env, original: str) -> None:
    (env.codex / "config.toml").write_bytes(original.encode())

    result = env.install("codex")

    _ok(result)
    assert (env.codex / "config.toml").read_bytes() == original.encode()
    assert "kept" in result.stdout


@needs_bash
def test_a_servers_key_that_is_not_an_object_is_refused_before_any_write(env: Env) -> None:
    original = '{"mcpServers": ["keep"], "a": 1}'
    (env.project / ".mcp.json").write_text(original)

    result = env.install("claude")

    assert result.returncode == 1
    assert "mcpServers" in result.stderr
    assert (env.project / ".mcp.json").read_text() == original
    assert not (env.project / ".claude").exists()


@needs_bash
def test_a_quote_or_backslash_in_the_base_url_stays_inside_the_strings(env: Env) -> None:
    base = 'https://o.example/"q\\z'
    (env.project / ".mcp.json").write_text('{"mcpServers": {"other": {}}}')

    result = env.run("--harness", "all", "--base-url", base)

    _ok(result)
    claude = json.loads((env.project / ".mcp.json").read_text())
    assert claude["mcpServers"]["orchestrator"]["url"] == f"{base}/mcp"
    assert set(claude["mcpServers"]["orchestrator"]) == {"type", "url", "headers"}
    opencode = json.loads((env.project / "opencode.json").read_text())
    assert opencode["mcp"]["orchestrator"]["url"] == f"{base}/mcp"
    codex = tomllib.loads((env.codex / "config.toml").read_text())
    assert codex["mcp_servers"] == {
        "orchestrator": {"url": f"{base}/mcp", "bearer_token_env_var": "ORCHESTRATOR_TOKEN"}
    }
    marker = json.loads((env.project / ".orchestrator" / "bootstrap.json").read_text())
    assert marker["base_url"] == base


@needs_bash
@pytest.mark.parametrize("flag", ["--base-url", "--web-url"])
def test_a_control_character_in_a_url_is_refused(env: Env, flag: str) -> None:
    result = env.run("--harness", "codex", flag, 'https://x.example\ncommand = "sh"')

    assert result.returncode == 1
    assert "control character" in result.stderr
    assert not (env.codex / "config.toml").exists()
    assert not (env.project / ".agents").exists()


# ── the beta.4 move ──────────────────────────────────────────────────────────


@needs_bash
def test_a_beta4_project_loses_its_kit(env: Env) -> None:
    orch = env.project / ".orchestrator"
    (orch / "bin").mkdir(parents=True)
    (orch / "kit.json").write_text("{}")
    (orch / "bin" / "orchestrator-watch").write_text("x")
    (env.project / ".env").write_text("ORCHESTRATOR_TOKEN=old\n")
    for d in (".claude/skills", ".agents/skills"):
        for name in OLD_SKILLS:
            (env.project / d / name / "references").mkdir(parents=True)
            (env.project / d / name / "SKILL.md").write_text("old")
            (env.project / d / name / "references" / "api.md").write_text("old")
    (env.project / ".claude/skills/mine").mkdir()
    (env.project / ".claude/skills/mine/SKILL.md").write_text("mine")

    result = env.install("claude")

    _ok(result)
    assert [p.name for p in (env.project / ".claude/skills/orchestrator").iterdir()] == ["SKILL.md"]
    assert sorted(p.name for p in (env.project / ".claude/skills").iterdir()) == [
        "mine",
        "orchestrator",
    ]
    assert not (env.project / ".agents/skills").exists() or not any(
        (env.project / ".agents/skills").iterdir()
    )
    assert not (orch / "bin").exists()
    assert not (orch / "kit.json").exists()
    assert (env.project / ".env").read_text() == "ORCHESTRATOR_TOKEN=old\n"
    assert str(orch / "bin") in result.stdout
    assert str(env.project / ".agents/skills/initiative-run") in result.stdout
    assert ".env" in result.stdout and "not read by the bootstrap" in result.stdout


# ── remote mode ──────────────────────────────────────────────────────────────


@needs_bash
def test_remote_mode_installs_from_the_served_archive(env: Env) -> None:
    result = env.run(
        "--harness",
        "claude",
        "--base-url",
        BASE,
        script=env.piped_script(),
        env={"ORCHESTRATOR_TOKEN": SECRET, "SHIM_ARCHIVE": env.archive()},
    )

    _ok(result)
    log = env.log.read_text()
    assert "/api/v1/kit/archive" in log
    assert f"Authorization: Bearer {SECRET}" in log
    assert (env.project / SKILL_CLAUDE).is_file()
    assert SECRET not in result.stdout + result.stderr
    for path in env.written_files():
        assert SECRET not in path.read_text()


@needs_bash
def test_remote_mode_without_the_variable_names_it(env: Env) -> None:
    result = env.run("--harness", "claude", "--base-url", BASE, script=env.piped_script())

    assert result.returncode != 0
    assert "ORCHESTRATOR_TOKEN" in result.stderr
    assert env.written_files() == []


@needs_bash
def test_remote_mode_reads_the_variable_the_flag_names(env: Env) -> None:
    result = env.run(
        "--harness",
        "claude",
        "--base-url",
        BASE,
        "--token-var",
        "MY_TOKEN",
        script=env.piped_script(),
        env={"MY_TOKEN": SECRET, "SHIM_ARCHIVE": env.archive()},
    )

    _ok(result)
    assert f"Authorization: Bearer {SECRET}" in env.log.read_text()


# ── the probe ────────────────────────────────────────────────────────────────


@needs_bash
def test_the_probe_prints_the_release_and_contract(env: Env) -> None:
    result = env.install(
        "claude", env={"ORCHESTRATOR_TOKEN": SECRET, "SHIM_VERSION_FILE": env.version_body()}
    )

    _ok(result)
    assert f"{BASE}/api/v1/version" in env.log.read_text()
    assert "9.9.9" in result.stdout
    assert "bootstrap_contract" in result.stdout
    assert SECRET not in result.stdout + result.stderr


@needs_bash
def test_a_higher_contract_is_a_difference_not_an_error(env: Env) -> None:
    result = env.install(
        "claude",
        env={"ORCHESTRATOR_TOKEN": SECRET, "SHIM_VERSION_FILE": env.version_body(contract=2)},
    )

    _ok(result)
    assert "refusal-bootstrap-contract" in result.stdout + result.stderr
    assert "2" in result.stdout + result.stderr


@needs_bash
def test_the_probe_is_skipped_without_the_variable(env: Env) -> None:
    result = env.install("claude")

    _ok(result)
    assert "ORCHESTRATOR_TOKEN" in result.stdout
    assert "skipped" in result.stdout
    assert "/api/v1/version" not in env.log.read_text()


@needs_bash
def test_a_refused_token_stops_naming_the_variable_not_the_value(env: Env) -> None:
    result = env.install("claude", env={"ORCHESTRATOR_TOKEN": SECRET, "SHIM_VERSION_CODE": "401"})

    assert result.returncode != 0
    assert "401" in result.stderr
    assert "ORCHESTRATOR_TOKEN" in result.stderr
    assert SECRET not in result.stdout + result.stderr
