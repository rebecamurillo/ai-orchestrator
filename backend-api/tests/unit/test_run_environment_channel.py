"""The harness env path never reads `project_channel` (story 3-4, AD-5 amendment).

`read_run_environment` builds the `ProjectContext` a dispatch hands to `env_for(attempt)`, and
`infrastructure/harness/env.py` builds the process env from it. Neither module names channel
storage, so a bot token has no route into a harness process.

Revised: story 3-4 review, 2026-11-02 — the behavioural test built a channel fake that the
reader never consulted, so it proved nothing; this static check is the stated proof.
"""

from __future__ import annotations

import ast
import inspect
from types import ModuleType

import pytest

from orchestrator.infrastructure.db import environment
from orchestrator.infrastructure.harness import env as harness_env


@pytest.mark.parametrize("module", [environment, harness_env], ids=lambda m: m.__name__)
def test_the_harness_env_path_names_no_channel_storage(module: ModuleType) -> None:
    source = inspect.getsource(module)
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    assert "project_channel" not in source
    assert "token_enc" not in source
    assert not any("Channel" in name or "chat" in name for name in imported)
