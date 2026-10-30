"""The per-harness setup scripts, held to the contract they exist to hold (AD-10, AD-5).

`scripts/harness/<name>.sh` is the only place a harness's environment and static config are
defined. Nothing in Epic 1 executes `install` — that happens at image build — so without
this module the four scripts could ship broken, non-executable, or carrying a credential,
and every gate would stay green until an Epic 5 adapter tried to use them.

Four properties are worth asserting mechanically:

- **They run.** `bash -n` parses each file, and each harness script answers an unknown verb
  with usage and exit 2. A script that cannot be sourced is caught here, not at build time.
- **`install` needs no gateway credential.** It runs as `agent` during `docker build`, where
  `LITELLM_API_KEY` and the Langfuse keys do not exist and must never be baked in. The guard
  therefore belongs to `configure` and `doctor`, and this module proves it is still there for
  those two: a scrubbed environment must refuse, naming the variable.
- **Config files carry names, not values (AD-10).** A harness config that interpolated
  `LITELLM_API_KEY` would write the key into `AGENT_HOME`; the per-attempt values arrive
  through the environment instead.
- **AD-5 holds by absence.** `GITHUB_TOKEN` and `LITELLM_SPEND_KEY` appear in no script.

The pinned versions are read back out of the scripts and compared with `.env.example`, so
the contract and the defaults cannot drift apart silently.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"

COMMON = "_common.sh"
HARNESSES = ("claude", "codex", "opencode")
#: `ensure` is the container-start reconcile of the installed CLI against its `*_VERSION` pin
#: (spec-harness-upgrade-survives-redeploy, 2026-10-22).
VERBS = ("install", "ensure", "configure", "doctor")

#: The `: "${NAME:=default}"` line in each script, against the contract line that pins it.
PINNED_VERSIONS = {
    "claude": "CLAUDE_CODE_VERSION",
    "codex": "CODEX_VERSION",
    "opencode": "OPENCODE_VERSION",
}

#: The npm package each harness installs, and how its CLI prints `--version`.
NPM_PACKAGES = {
    "claude": "@anthropic-ai/claude-code",
    "codex": "@openai/codex",
    "opencode": "opencode-ai",
}
VERSION_LINE = {
    "claude": "{version} (Claude Code)",
    "codex": "codex-cli {version}",
    "opencode": "{version}",
}

#: Never in a harness process, so never in a harness script (AD-5).
FORBIDDEN_NAMES = ("GITHUB_TOKEN", "LITELLM_SPEND_KEY")

#: The exit code a shell convention reserves for "wrong usage".
USAGE_EXIT_CODE = 2

#: What `configure` and `doctor` require before they will write or probe anything.
REQUIRED_AT_CONFIGURE = (
    "LITELLM_BASE_URL",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


def script(name: str) -> Path:
    return HARNESS_DIR / f"{name}.sh"


def text(name: str) -> str:
    path = script(name)
    assert path.is_file(), f"{path} is missing"
    return path.read_text()


def code(name: str) -> str:
    """The script with its whole-line comments dropped.

    AD-5 is about what a script *does*, and `_common.sh` documents the two names it must
    never carry. Reading through the comments would make that documentation a violation.
    """
    kept = [line for line in text(name).splitlines() if not line.strip().startswith("#")]
    return "\n".join(kept) + "\n"


def _run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        list(argv),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# ── the scripts exist and run ────────────────────────────────────────────────


@pytest.mark.parametrize("name", (COMMON.removesuffix(".sh"), *HARNESSES))
def test_the_script_is_committed(name: str) -> None:
    assert script(name).is_file()


@pytest.mark.parametrize("name", HARNESSES)
def test_a_harness_script_is_executable(name: str) -> None:
    """`docker compose exec backend-api scripts/harness/claude.sh doctor` runs it directly."""
    mode = script(name).stat().st_mode

    assert mode & stat.S_IXUSR, f"{name}.sh: owner cannot execute it"
    assert mode & stat.S_IXOTH, f"{name}.sh: the container's user cannot execute it"


@pytest.mark.parametrize("name", (COMMON.removesuffix(".sh"), *HARNESSES))
def test_the_script_parses(name: str) -> None:
    result = _run("bash", "-n", str(script(name)))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_an_unknown_verb_prints_usage_and_exits_two(name: str) -> None:
    """Sourcing `_common.sh` must not itself need configuration — this is what proves it."""
    result = _run("bash", str(script(name)), "nonsense", env={"PATH": os.environ["PATH"]})

    assert result.returncode == USAGE_EXIT_CODE, result.stdout + result.stderr
    assert "usage" in result.stderr


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize("verb", VERBS)
def test_the_script_implements_every_verb(name: str, verb: str) -> None:
    assert re.search(rf"^{verb}\(\) \{{", text(name), re.MULTILINE), f"{name}.sh: no {verb}()"


# ── install needs no credential; configure and doctor refuse without one ─────


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize("verb", ("configure", "doctor"))
def test_configure_and_doctor_check_the_environment_first(name: str, verb: str) -> None:
    lines = code(name).splitlines()
    dispatch = next(line for line in lines if f"{verb})" in line or "|doctor)" in line)

    assert "require_harness_env" in dispatch, f"{name}.sh: {verb} must call require_harness_env"


@pytest.mark.parametrize("name", HARNESSES)
def test_install_does_not_check_the_gateway_environment(name: str) -> None:
    """It runs during `docker build`, where those values do not exist and must not be baked in."""
    dispatch = next(line for line in code(name).splitlines() if "install)" in line)

    assert "require_harness_env" not in dispatch, dispatch


@pytest.mark.parametrize("name", HARNESSES)
def test_configure_refuses_with_nothing_configured(name: str) -> None:
    """A container that configured a harness from an empty environment would serve broken."""
    result = _run(
        "bash",
        str(script(name)),
        "configure",
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "")},
    )

    assert result.returncode != 0
    assert any(variable in result.stderr for variable in REQUIRED_AT_CONFIGURE), result.stderr


def test_the_guard_names_every_variable_configure_needs() -> None:
    body = text(COMMON.removesuffix(".sh"))
    guard = body[body.index("require_harness_env()") :]

    for variable in REQUIRED_AT_CONFIGURE:
        assert f"${{{variable}:?" in guard, variable


# ── AD-10: names, not values; AD-5: two names never appear ──────────────────


@pytest.mark.parametrize("name", (COMMON.removesuffix(".sh"), *HARNESSES))
@pytest.mark.parametrize("forbidden", FORBIDDEN_NAMES)
def test_no_script_names_a_credential_a_harness_never_receives(name: str, forbidden: str) -> None:
    assert forbidden not in code(name), f"{name}.sh: {forbidden} (AD-5)"


@pytest.mark.parametrize("name", HARNESSES)
def test_a_config_file_is_written_with_variable_names_not_values(name: str) -> None:
    """`env_key`, `{env:...}` and the adapter's environment carry the key; the file never does."""
    assert "${LITELLM_API_KEY" not in code(name), f"{name}.sh: expands the key into its config"


def test_the_environment_contract_carries_the_model_key_and_not_the_spend_key() -> None:
    body = code(COMMON.removesuffix(".sh"))
    contract = body[body.index("HARNESS_ENV_CONTRACT=(") :].split(")", 1)[0]

    assert "LITELLM_API_KEY" in contract
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in contract


# ── the pinned versions agree with the contract ──────────────────────────────


@pytest.mark.parametrize(("name", "variable"), sorted(PINNED_VERSIONS.items()))
def test_the_pinned_version_matches_the_contract(name: str, variable: str) -> None:
    """A script default drifting from `.env.example` would install a version nobody chose."""
    contract = parse_env_example(ENV_EXAMPLE)
    match = re.search(rf"\$\{{{variable}:=([^}}]+)\}}", text(name))

    assert match, f"{name}.sh: no default for {variable}"
    assert match.group(1) == contract[variable]


def test_the_method_version_matches_the_contract() -> None:
    contract = parse_env_example(ENV_EXAMPLE)
    match = re.search(r"\$\{BMAD_VERSION:=([^}]+)\}", text(COMMON.removesuffix(".sh")))

    assert match
    assert match.group(1) == contract["BMAD_VERSION"]


def test_the_agent_home_default_matches_the_contract() -> None:
    contract = parse_env_example(ENV_EXAMPLE)
    match = re.search(r"\$\{AGENT_HOME:=([^}]+)\}", text(COMMON.removesuffix(".sh")))

    assert match
    assert match.group(1) == contract["AGENT_HOME"]


# ── ensure: the installed CLI reconciled against its pin at container start ──
#
# spec-harness-upgrade-survives-redeploy (2026-10-29). Two scratch npm prefixes stand in for
# the image copy (`/opt/harness-image`) and the `harness-bin` volume (`/opt/harness-cli`);
# `npm` and `timeout` are shims on a PATH that holds nothing else of the operator's machine,
# so no test here reaches the registry. The npm shim lays the package down under the
# `--prefix` it is given, so the re-read after npm sees what npm wrote.

PIN = "9.9.9"
OTHER = "1.0.0"
#: Enough of the system for bash, awk, head, cp and dirname, and no real harness CLI or npm.
SYSTEM_PATH = "/usr/bin:/bin"
HARNESS_PREFIX = "/opt/harness-cli"
HARNESS_IMAGE_PREFIX = "/opt/harness-image"
#: The pin shape every reader of a `*_VERSION` pin accepts, written once per file.
PLAIN_VERSION = r"^[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}([-+][0-9A-Za-z.-]+)?$"


def _cli_text(name: str, version: str, marker: str = "") -> str:
    """A CLI whose `--version` is noisy: a stderr warning first, a trailing stdout line after."""
    line = VERSION_LINE[name].format(version=version)
    return (
        "#!/bin/sh\n"
        f"# {marker}\n"
        "echo 'warning: something 0.0.1 changed' >&2\n"
        f"echo '{line}'\n"
        "echo 'update available: 7.7.7'\n"
    )


def _lay_down(prefix: Path, name: str, version: str, marker: str = "") -> Path:
    """The layout `npm install -g --prefix` leaves: the package, and a relative bin link."""
    package = prefix / "lib" / "node_modules" / NPM_PACKAGES[name]
    package.mkdir(parents=True, exist_ok=True)
    cli = package / "cli"
    cli.write_text(_cli_text(name, version, marker))
    cli.chmod(0o755)
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    link = prefix / "bin" / name
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(Path("..") / "lib" / "node_modules" / NPM_PACKAGES[name] / "cli")
    return cli


def _installed_cli(prefix: Path, name: str) -> str | None:
    link = prefix / "bin" / name
    return link.read_text() if link.exists() else None


@dataclass
class Ensured:
    result: subprocess.CompletedProcess[str]
    npm_calls: list[str]
    timeout_calls: list[str]
    volume: Path
    image: Path


def _ensure(  # noqa: PLR0913 — one keyword per state a test varies
    name: str,
    tmp_path: Path,
    *,
    installed: str | None,
    image: str | None = None,
    npm: str = "the pin",
    pin: str = PIN,
    verb: str = "ensure",
    on_path: str | None = None,
    shims: dict[str, str] | None = None,
    setup: Callable[[Path], None] | None = None,
) -> Ensured:
    """`npm` is what the shim does: lay down "the pin", "fail", or lay down that version."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    volume = tmp_path / "harness-cli"
    image_prefix = tmp_path / "harness-image"
    volume.mkdir()
    image_prefix.mkdir()
    if installed is not None:
        _lay_down(volume, name, installed, marker="volume")
    if image is not None:
        _lay_down(image_prefix, name, image, marker="image")
    if setup is not None:
        setup(volume)
    for shim_name, body in (shims or {}).items():
        (bin_dir / shim_name).write_text(body)
        (bin_dir / shim_name).chmod(0o755)
    if on_path is not None:
        cli = bin_dir / name
        cli.write_text(_cli_text(name, on_path))
        cli.chmod(0o755)
    npm_log = tmp_path / "npm.log"
    timeout_log = tmp_path / "timeout.log"
    laid = tmp_path / "npm-package"
    _lay_down(laid, name, pin if npm == "the pin" else npm, marker="npm")
    package = NPM_PACKAGES[name]
    npm_shim = bin_dir / "npm"
    npm_shim.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{npm_log}"\n'
        + (
            "exit 1\n"
            if npm == "fail"
            else 'prefix=""\n'
            'while [ $# -gt 0 ]; do [ "$1" = --prefix ] && prefix="$2"; shift; done\n'
            f'mkdir -p "$prefix/lib/node_modules/{package}" "$prefix/bin"\n'
            f'cp -R "{laid}/lib/node_modules/{package}/." "$prefix/lib/node_modules/{package}/"\n'
            f'cp -R "{laid}/bin/{name}" "$prefix/bin/{name}"\n'
        )
    )
    npm_shim.chmod(0o755)
    timeout_shim = bin_dir / "timeout"
    timeout_shim.write_text(f'#!/bin/sh\necho "$*" >> "{timeout_log}"\nshift\nexec "$@"\n')
    timeout_shim.chmod(0o755)
    bash = shutil.which("bash")
    assert bash
    result = _run(
        bash,
        str(script(name)),
        verb,
        env={
            "PATH": f"{bin_dir}:{SYSTEM_PATH}",
            "HOME": str(tmp_path),
            "AGENT_HOME": str(tmp_path / "home"),
            "HARNESS_PREFIX": str(volume),
            "HARNESS_IMAGE_PREFIX": str(image_prefix),
            PINNED_VERSIONS[name]: pin,
        },
    )
    return Ensured(
        result=result,
        npm_calls=npm_log.read_text().splitlines() if npm_log.exists() else [],
        timeout_calls=timeout_log.read_text().splitlines() if timeout_log.exists() else [],
        volume=volume,
        image=image_prefix,
    )


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_does_not_check_the_gateway_environment(name: str) -> None:
    """It runs before `configure`, and reads nothing but the pin."""
    dispatch = next(line for line in code(name).splitlines() if "ensure)" in line)

    assert "require_harness_env" not in dispatch, dispatch


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_with_the_volume_at_the_pin_runs_no_npm(name: str, tmp_path: Path) -> None:
    ran = _ensure(name, tmp_path, installed=PIN, image=OTHER)

    assert ran.result.returncode == 0, ran.result.stderr
    assert ran.npm_calls == []
    assert f"{name} {PIN} at pin" in ran.result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_parses_only_the_first_stdout_line_of_version(name: str, tmp_path: Path) -> None:
    """The fake CLI warns on stderr and prints a second stdout line; neither is the version."""
    ran = _ensure(name, tmp_path, installed=PIN)

    assert ran.result.returncode == 0, ran.result.stderr
    assert ran.npm_calls == []
    assert "7.7.7" not in ran.result.stderr
    assert "0.0.1" not in ran.result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_copies_the_image_copy_when_it_is_at_the_pin(name: str, tmp_path: Path) -> None:
    """A release that raised the pin brings the CLI in its image: no registry needed at start."""
    ran = _ensure(name, tmp_path, installed=OTHER, image=PIN)

    assert ran.result.returncode == 0, ran.result.stderr
    assert ran.npm_calls == []
    assert f"{name} {PIN} from image" in ran.result.stderr
    assert _installed_cli(ran.volume, name) == _installed_cli(ran.image, name)
    assert (ran.volume / "bin" / name).is_symlink()


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_seeds_an_empty_volume_from_the_image_copy(name: str, tmp_path: Path) -> None:
    ran = _ensure(name, tmp_path, installed=None, image=PIN)

    assert ran.result.returncode == 0, ran.result.stderr
    assert ran.npm_calls == []
    assert _installed_cli(ran.volume, name) == _installed_cli(ran.image, name)


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_restores_a_tampered_volume_copy_from_the_image(name: str, tmp_path: Path) -> None:
    """The volume copy claims the pin but is not what the image shipped: replaced, every start."""
    ran = _ensure(name, tmp_path, installed=PIN, image=PIN)

    assert ran.result.returncode == 0, ran.result.stderr
    assert ran.npm_calls == []
    restored = _installed_cli(ran.volume, name)
    assert restored is not None
    assert "# image" in restored
    assert "# volume" not in restored


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_reads_versions_from_the_prefixes_not_the_path(name: str, tmp_path: Path) -> None:
    """A CLI at the pin earlier on PATH does not stand in for the volume's copy."""
    ran = _ensure(name, tmp_path, installed=OTHER, on_path=PIN)

    assert ran.result.returncode == 0, ran.result.stderr
    assert len(ran.npm_calls) == 1
    assert f"{name} {OTHER} → {PIN}" in ran.result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_off_the_pin_installs_the_pin_once(name: str, tmp_path: Path) -> None:
    ran = _ensure(name, tmp_path, installed=OTHER, image=OTHER)

    assert ran.result.returncode == 0, ran.result.stderr
    assert len(ran.npm_calls) == 1
    staging = f"{ran.volume}/.staging/"
    argv = ran.npm_calls[0].split()
    assert argv[:2] == ["install", "-g"]
    assert argv[argv.index("--prefix") + 1].startswith(staging)
    assert argv[-1] == f"{NPM_PACKAGES[name]}@{PIN}"
    assert f"{name} {OTHER} → {PIN}" in ran.result.stderr
    assert f"{name} {PIN} at pin" in ran.result.stderr
    installed = _installed_cli(ran.volume, name)
    assert installed is not None
    assert "# npm" in installed
    assert not any((ran.volume / ".staging").iterdir())


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_runs_npm_with_no_fetch_retries_and_bounded(name: str, tmp_path: Path) -> None:
    """npm's own fetch retries would be a silent retry (hard rule 7); a stall must end."""
    ran = _ensure(name, tmp_path, installed=OTHER)

    assert ran.result.returncode == 0, ran.result.stderr
    assert "--fetch-retries=0" in ran.npm_calls[0].split()
    assert "--fetch-timeout=60000" in ran.npm_calls[0].split()
    assert any(call.startswith("120 npm install -g ") for call in ran.timeout_calls)
    version_reads = [call for call in ran.timeout_calls if call.endswith(" --version")]
    assert version_reads
    assert all(call.startswith("30 ") for call in version_reads)


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_with_the_cli_absent_installs_the_pin(name: str, tmp_path: Path) -> None:
    """A `harness-bin` volume created from an older image, never seeded with this CLI."""
    ran = _ensure(name, tmp_path, installed=None)

    assert ran.result.returncode == 0, ran.result.stderr
    assert len(ran.npm_calls) == 1
    assert f"absent → {PIN}" in ran.result.stderr
    assert _installed_cli(ran.volume, name) is not None


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_fails_when_the_pin_cannot_be_installed(name: str, tmp_path: Path) -> None:
    """No retry (hard rule 7): one npm call, then a non-zero exit naming both versions."""
    ran = _ensure(name, tmp_path, installed=OTHER, npm="fail")

    assert ran.result.returncode != 0
    assert len(ran.npm_calls) == 1
    assert name in ran.result.stderr
    assert OTHER in ran.result.stderr
    assert PIN in ran.result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_a_failed_npm_leaves_the_previous_copy_and_no_staging(name: str, tmp_path: Path) -> None:
    ran = _ensure(name, tmp_path, installed=OTHER, npm="fail")

    previous = _installed_cli(ran.volume, name)
    assert previous is not None
    assert "# volume" in previous
    assert VERSION_LINE[name].format(version=OTHER) in previous
    staging = ran.volume / ".staging"
    assert not staging.exists() or not any(staging.iterdir())


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_fails_when_the_installed_cli_is_still_off_the_pin(
    name: str, tmp_path: Path
) -> None:
    """npm exits 0 but the re-read version differs: refused, the previous copy kept."""
    ran = _ensure(name, tmp_path, installed=OTHER, npm="2.0.0")

    assert ran.result.returncode != 0
    assert len(ran.npm_calls) == 1
    assert "2.0.0" in ran.result.stderr
    assert PIN in ran.result.stderr
    assert f"{name} {PIN} at pin" not in ran.result.stderr
    previous = _installed_cli(ran.volume, name)
    assert previous is not None
    assert "# volume" in previous
    staging = ran.volume / ".staging"
    assert not staging.exists() or not any(staging.iterdir())


#: `mv` that refuses to move a staged `.next` copy into place, and does everything else.
MV_FAILS_ON_NEXT = '#!/bin/sh\ncase "$1" in *.next) exit 1 ;; esac\nexec /bin/mv "$@"\n'


def _runs_at(prefix: Path, name: str) -> str:
    """The first stdout line the volume's bin link prints for `--version`."""
    result = _run(str(prefix / "bin" / name), "--version")
    return result.stdout.splitlines()[0] if result.stdout else ""


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize("source", ["npm", "image"])
def test_a_failed_swap_leaves_the_previous_copy_runnable(
    name: str, source: str, tmp_path: Path
) -> None:
    ran = _ensure(
        name,
        tmp_path,
        installed=OTHER,
        image=PIN if source == "image" else None,
        shims={"mv": MV_FAILS_ON_NEXT},
    )

    if source == "npm":
        assert ran.result.returncode != 0
        assert f"installed: {OTHER}" in ran.result.stderr
    assert _runs_at(ran.volume, name) == VERSION_LINE[name].format(version=OTHER)
    modules = ran.volume / "lib" / "node_modules" / NPM_PACKAGES[name]
    assert not Path(f"{modules}.next").exists()
    assert not Path(f"{modules}.prev").exists()
    assert not (ran.volume / "bin" / f"{name}.prev").exists()


@pytest.mark.parametrize("name", HARNESSES)
def test_ensure_restores_a_copy_an_interrupted_start_left_aside(name: str, tmp_path: Path) -> None:
    """The live copy was renamed to `.prev` and the start died before the new one landed."""

    def interrupted(volume: Path) -> None:
        modules = volume / "lib" / "node_modules" / NPM_PACKAGES[name]
        modules.rename(f"{modules}.prev")
        (volume / "bin" / name).rename(volume / "bin" / f"{name}.prev")
        Path(f"{modules}.next").mkdir()

    ran = _ensure(name, tmp_path, installed=PIN, setup=interrupted)

    assert ran.result.returncode == 0, ran.result.stderr
    assert ran.npm_calls == []
    assert f"{name} {PIN} at pin" in ran.result.stderr
    assert _runs_at(ran.volume, name) == VERSION_LINE[name].format(version=PIN)
    modules = ran.volume / "lib" / "node_modules" / NPM_PACKAGES[name]
    assert not Path(f"{modules}.next").exists()
    assert not Path(f"{modules}.prev").exists()


@pytest.mark.parametrize("name", HARNESSES)
def test_a_staging_directory_that_cannot_be_created_is_named(name: str, tmp_path: Path) -> None:
    def blocked(volume: Path) -> None:
        (volume / ".staging").write_text("a file where the directory goes")

    ran = _ensure(name, tmp_path, installed=OTHER, setup=blocked)

    assert ran.result.returncode != 0
    assert ran.npm_calls == []
    assert f"cannot create {ran.volume}/.staging/{name}" in ran.result.stderr


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize(
    "pin", ["latest", "^2.1", "2.1", "v2.1.0", "2.1.0 ; rm -rf /", "1234567890.0.0"]
)
def test_ensure_refuses_a_pin_that_is_not_a_plain_version(
    name: str, pin: str, tmp_path: Path
) -> None:
    ran = _ensure(name, tmp_path, installed=OTHER, image=pin, pin=pin)

    assert ran.result.returncode != 0
    assert ran.npm_calls == []
    assert PINNED_VERSIONS[name] in ran.result.stderr


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize("pin", ["latest", "^2.1"])
def test_install_refuses_a_pin_that_is_not_a_plain_version(
    name: str, pin: str, tmp_path: Path
) -> None:
    """The image build checks the pin before npm, exactly as `ensure` does."""
    ran = _ensure(name, tmp_path, installed=None, pin=pin, verb="install")

    assert ran.result.returncode != 0
    assert ran.npm_calls == []
    assert PINNED_VERSIONS[name] in ran.result.stderr


def test_ensure_refuses_an_empty_pin(tmp_path: Path) -> None:
    """The scripts' `:=` default fills an empty variable, so the helper is called directly."""
    npm_log = tmp_path / "npm.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(f'#!/bin/sh\necho "$*" >> "{npm_log}"\n')
    npm.chmod(0o755)
    result = _run(
        "bash",
        "-c",
        f'source "{script(COMMON.removesuffix(".sh"))}"; '
        'v() { echo 1.0.0; }; ensure_cli_at_pin claude true pkg CLAUDE_CODE_VERSION "" v',
        env={
            "PATH": f"{bin_dir}:{SYSTEM_PATH}",
            "HARNESS_PREFIX": str(tmp_path / "volume"),
            "HARNESS_IMAGE_PREFIX": str(tmp_path / "image"),
        },
    )

    assert result.returncode != 0
    assert not npm_log.exists()
    assert "CLAUDE_CODE_VERSION" in result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_install_and_ensure_share_one_npm_install_line(name: str) -> None:
    """The package name is written once, so the image build and the boot reconcile agree."""
    assert code(name).count("npm install -g") == 0
    assert code(COMMON.removesuffix(".sh")).count("npm install -g") == 1


@pytest.mark.parametrize("name", HARNESSES)
def test_install_writes_the_image_copy(name: str) -> None:
    """`install` targets the image-only prefix; the Dockerfile copies it into the volume's."""
    install = re.search(r"^install\(\) \{\n(.*?)^\}", code(name), re.MULTILINE | re.DOTALL)
    assert install

    assert 'npm_install_cli "${HARNESS_IMAGE_PREFIX}"' in install.group(1)


def test_the_harness_prefixes_are_named_once() -> None:
    common = code(COMMON.removesuffix(".sh"))

    assert f'"${{HARNESS_PREFIX:={HARNESS_PREFIX}}}"' in common
    assert f'"${{HARNESS_IMAGE_PREFIX:={HARNESS_IMAGE_PREFIX}}}"' in common
    assert "npm install -g --prefix" in common


def test_the_plain_version_pattern_is_the_same_wherever_a_pin_is_read() -> None:
    """`ensure`, `install.sh` and `push-images.sh` must agree on what a pin may be."""
    for path in (
        HARNESS_DIR / COMMON,
        REPO_ROOT / "deploy" / "install.sh",
        REPO_ROOT / "scripts" / "push-images.sh",
        REPO_ROOT / ".github" / "workflows" / "release.yml",
    ):
        assert f"'{PLAIN_VERSION}'" in path.read_text(), path


# ── ensure-all.sh: one refused harness never stops the start ─────────────────

ENSURE_ALL = HARNESS_DIR / "ensure-all.sh"


def test_ensure_all_is_committed_and_executable() -> None:
    mode = ENSURE_ALL.stat().st_mode

    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXOTH
    assert _run("bash", "-n", str(ENSURE_ALL)).returncode == 0


@pytest.mark.parametrize("failing", HARNESSES)
def test_ensure_all_continues_past_a_refused_harness_and_exits_zero(
    failing: str, tmp_path: Path
) -> None:
    """Copied beside stub `<name>.sh` scripts: the real ones are not run here."""
    shutil.copy2(ENSURE_ALL, tmp_path / "ensure-all.sh")
    ran = tmp_path / "ran.log"
    for name in HARNESSES:
        stub = tmp_path / f"{name}.sh"
        rc = 1 if name == failing else 0
        stub.write_text(f'#!/bin/sh\necho "{name} $1" >> "{ran}"\nexit {rc}\n')
        stub.chmod(0o755)

    result = _run(str(tmp_path / "ensure-all.sh"), env={"PATH": SYSTEM_PATH})

    assert result.returncode == 0, result.stderr
    assert ran.read_text().splitlines() == [f"{name} ensure" for name in HARNESSES]
    assert f"[harness:{failing}] refused until the next start" in result.stderr
    for name in HARNESSES:
        if name != failing:
            assert f"[harness:{name}] refused" not in result.stderr
