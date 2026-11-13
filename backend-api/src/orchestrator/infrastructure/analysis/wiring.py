"""The composition of the code analysis: tools, lookups, scratch and the two entry forms."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from uuid import UUID

from orchestrator.application.analysis.run_analysis import AnalysisDeps, analyse_run
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.infrastructure.analysis.package_lookup import HttpPackageLookup
from orchestrator.infrastructure.analysis.tools import ProcessAnalysisTools
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.crypto.fernet import FernetCrypto
from orchestrator.infrastructure.db.environment import read_run_environment
from orchestrator.infrastructure.db.writers import SessionFactory, open_analysis_ports
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.workspace import FsWorkspace


def build_analysis(
    settings: Settings, session_factory: SessionFactory, git: Git, runner: ProcessRunner
) -> tuple[Callable[[UUID], Sequence[Analysis]], Callable[[UUID, UUID], Sequence[Analysis]]]:
    """`(pending, calculating)`: the first stores analyses with no calculation, the second
    stores them under the calculation it is given."""
    tools = ProcessAnalysisTools(runner, settings.work_dir / "logs" / "analysis")

    def project_env(run_id: UUID) -> Mapping[str, str]:
        found = read_run_environment(
            session_factory,
            settings.bmad_version,
            run_id,
            crypto=partial(FernetCrypto, settings.orchestrator_secret_key.get_secret_value()),
        )
        return {} if found is None else found.project.env_vars

    deps = AnalysisDeps(
        git=git,
        tools=tools,
        lookup=HttpPackageLookup(tools),
        lookups=settings.analysis_lookups == "on",
        scratch_root=FsWorkspace(str(settings.work_dir / "analysis")),
        work_dir=settings.work_dir,
        clock=SystemClock(),
        new_id=new_id,
        runner=runner,
        command_timeout_min=settings.analysis_command_timeout_min,
        project_env=project_env,
    )
    writes = partial(open_analysis_ports, session_factory)

    def calculating(run_id: UUID, calculation_id: UUID) -> Sequence[Analysis]:
        return analyse_run(deps, writes, run_id, calculation_id)

    def pending(run_id: UUID) -> Sequence[Analysis]:
        return analyse_run(deps, writes, run_id, None)

    return pending, calculating
