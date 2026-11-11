import os
import stat
from pathlib import Path

import pytest

import guard


def _docker_shim(tmp_path: Path, monkeypatch, body: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "docker"
    shim.write_text(f"#!/bin/sh\n{body}\n")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir))


@pytest.mark.parametrize(
    "name", ["aio", "aio-host", "ai-orchestrator", "ai-orchestrator-host", "my-stack"]
)
def test_check_project_refuses_production_and_unprefixed_names(name):
    with pytest.raises(guard.GuardRefusal, match=name):
        guard.check_project(name)


def test_check_project_refuses_a_running_project(tmp_path, monkeypatch):
    _docker_shim(tmp_path, monkeypatch, 'echo \'[{"Name":"aio-deploy-busy"}]\'')
    with pytest.raises(guard.GuardRefusal, match="aio-deploy-busy"):
        guard.check_project("aio-deploy-busy")


def test_check_project_refuses_when_compose_ls_fails(tmp_path, monkeypatch):
    _docker_shim(tmp_path, monkeypatch, "exit 1")
    with pytest.raises(guard.GuardRefusal, match="docker compose ls"):
        guard.check_project("aio-deploy-ok")


def test_check_project_refuses_when_docker_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(guard.GuardRefusal, match="docker compose ls"):
        guard.check_project("aio-deploy-ok")


def test_check_project_accepts_an_idle_prefixed_name(tmp_path, monkeypatch):
    _docker_shim(tmp_path, monkeypatch, "echo '[]'")
    assert guard.check_project("aio-deploy-ok") is None


def test_check_folder_refuses_the_production_home_and_children(tmp_path):
    with pytest.raises(guard.GuardRefusal):
        guard.check_folder(guard.PRODUCTION_HOME)
    with pytest.raises(guard.GuardRefusal):
        guard.check_folder(guard.PRODUCTION_HOME / "data")


def test_check_folder_resolves_symlinks(tmp_path):
    link = tmp_path / "link"
    os.symlink(guard.PRODUCTION_HOME, link)
    with pytest.raises(guard.GuardRefusal):
        guard.check_folder(link)


def test_check_folder_accepts_a_plain_folder(tmp_path):
    assert guard.check_folder(tmp_path) is None


@pytest.mark.parametrize(
    "argv",
    [["docker", "login", "ghcr.io"], ["/usr/bin/docker", "--config", "x", "login"]],
)
def test_check_argv_refuses_docker_login(argv):
    with pytest.raises(guard.GuardRefusal, match="login"):
        guard.check_argv(argv)


def test_check_argv_accepts_other_docker_commands():
    assert guard.check_argv(["docker", "ps"]) is None
