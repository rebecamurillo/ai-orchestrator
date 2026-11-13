"""`ProcessAnalysisTools`: the `AnalysisTools` port over a `ProcessRunner`."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.process import ProcessRunner

VERSION_ARGS: Mapping[str, tuple[str, ...]] = {"gitleaks": ("version",)}
DEFAULT_VERSION_ARGS = ("--version",)
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
UNKNOWN_VERSION = "unknown"
VERSION_TIMEOUT_MIN = 1.0
#: The shell's "command not found" code, for a tool that is missing or cannot be executed.
NOT_STARTED_EXIT = 127


class ProcessAnalysisTools:
    def __init__(
        self, runner: ProcessRunner, log_dir: Path, binaries: Mapping[str, str] | None = None
    ) -> None:
        self._runner = runner
        self._log_dir = log_dir
        self._binaries = dict(binaries or {})
        self._versions: dict[str, str] = {}

    def run(self, tool: str, args: Sequence[str], cwd: Path, timeout: float) -> ToolRun:
        version = self._version(tool)
        exit_code, timed_out, output = self._execute(tool, args, cwd, timeout)
        return ToolRun(
            exit=None if timed_out else exit_code,
            stdout=output,
            stderr="",
            version=version,
            timed_out=timed_out,
        )

    def version(self, tool: str) -> str:
        return self._version(tool)

    def _executable(self, tool: str) -> str:
        return self._binaries.get(tool, tool)

    def _version(self, tool: str) -> str:
        """Only a version actually read is cached: a failed probe is retried on the next run."""
        if tool not in self._versions:
            flags = VERSION_ARGS.get(tool, DEFAULT_VERSION_ARGS)
            _, _, output = self._execute(tool, flags, None, VERSION_TIMEOUT_MIN)
            found = VERSION_PATTERN.search(output)
            if found is None:
                return UNKNOWN_VERSION
            self._versions[tool] = found.group(0)
        return self._versions[tool]

    def _execute(
        self, tool: str, args: Sequence[str], cwd: Path | None, timeout: float
    ) -> tuple[int | None, bool, str]:
        executable = self._executable(tool)
        log = self._log_dir / f"{uuid.uuid4().hex}.log"
        try:
            handle = self._runner.start(
                [executable, *args], cwd=cwd, env={}, timeout_min=timeout, log_path=log
            )
            outcome = self._runner.wait(handle)
            output = log.read_text(errors="replace") if log.exists() else ""
        except OSError as error:
            return NOT_STARTED_EXIT, False, f"{executable}: {error.strerror or error}"
        finally:
            log.unlink(missing_ok=True)
        return outcome.exit_code, outcome.timed_out, output
