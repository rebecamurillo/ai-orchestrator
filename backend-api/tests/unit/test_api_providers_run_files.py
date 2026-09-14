"""The run-files providers, split out of `api/providers.py` at the 400-line cap.

Two claims. The first is identity: `api/providers.py` re-exports these three names, and a
re-export must be the same function object — `app.dependency_overrides` keys on identity,
so a copy would silently un-override every frozen run-files router test
(`test_run_files_router.py`, `test_run_files_write_router.py`, `test_run_files_diff_router.py`).

The second is the on-demand session: `run_files_diff_ports` reads `?diff` itself and
yields `None` without touching `app.state` when it is absent, so the file and tree modes
that share the route never pay for a session they do not open.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from orchestrator.api import providers, providers_run_files
from orchestrator.api.providers_run_files import (
    run_files_diff_ports,
    run_files_ports,
    run_files_write_ports,
)


def test_the_providers_module_re_exports_the_same_function_objects() -> None:
    assert providers.run_files_ports is providers_run_files.run_files_ports
    assert providers.run_files_write_ports is providers_run_files.run_files_write_ports
    assert providers.run_files_diff_ports is providers_run_files.run_files_diff_ports


def test_each_provider_is_importable_where_the_router_imports_it() -> None:
    """`routers/run_files.py` imports the trio from `api/providers.py`; both spellings
    must keep resolving, or the split becomes a route-table break."""
    assert callable(run_files_ports)
    assert callable(run_files_write_ports)
    assert callable(run_files_diff_ports)


def test_diff_ports_without_the_query_flag_yields_none_and_opens_nothing() -> None:
    request = Request({"type": "http", "app": FastAPI()})

    produced = list(run_files_diff_ports(request, diff=False))

    assert produced == [None]
