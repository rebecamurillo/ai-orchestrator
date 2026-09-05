"""The `Git` adapter: the only module in this system that starts a git process.

**How the credential reaches git, and nowhere else (AD-5, hard rule 5).** Git already has an
interface for asking a program for a credential — `GIT_ASKPASS` — and that is the one this
adapter uses. The token is put in a single private environment variable of a single
subprocess; `askpass.sh` echoes it when git asks. It is never an argument, never in a URL,
never in a git config and never written to a file, so it cannot end up in `ps` output, in a
remote URL under `WORK_DIR`, or in anything this process stores.

**The environment is built, not inherited.** A git hook or a credential helper started by
one of these commands sees `PATH`, an empty `HOME`, and the four variables below — not the
backend's own environment, which holds `ORCHESTRATOR_SECRET_KEY`, `DATABASE_URL` and the
gateway keys. `HOME` points at a private empty directory so no user `.gitconfig` can rewrite
a URL or install a helper under this process, and `GIT_CONFIG_NOSYSTEM=1` does the same for
`/etc/gitconfig`. `-c credential.helper=` on every invocation clears any helper that a config
this adapter did not read might still name, and `GIT_TERMINAL_PROMPT=0` means a command that
would have waited for a human fails instead of hanging.

**`askpass.sh` is copied, not executed in place.** A wheel install does not preserve an
executable bit and the package directory may be read-only, so the script is copied once per
adapter into a 0700 file in a private temporary directory.

**Every failure is a `GitError` whose output is redacted**, and a command that outlives its
timeout is a failure with `timeout after {n} s` — not a process left running and not an
exception the caller cannot report. A `url` and a `default_branch` are values the Operator
typed, so they are passed after `--`: without it a value beginning with `-` would be read as
a git option rather than as the operand it is.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import weakref
from pathlib import Path

from orchestrator.domain.ports.git import CloneResult, GitError, RemoteRef
from orchestrator.infrastructure.git.redact import redact

#: How long any one git command may take before it is a failed line.
TIMEOUT_SECONDS = 120

#: The exit code reported for a command that never exited.
TIMEOUT_EXIT_CODE = -1

#: The variable `askpass.sh` reads, and the only place the token exists at run time.
ASKPASS_TOKEN_VAR = "ORCHESTRATOR_GIT_TOKEN"
ASKPASS_NAME = "askpass.sh"

#: `rwx` for the owner and nothing for anyone else: git runs it, no other user reads it.
ASKPASS_MODE = 0o700

#: Where a base clone's origin refs live, and the ref namespace `read_file` prefers.
ORIGIN = "origin"
REMOTE_REFSPEC = "+refs/heads/*:refs/remotes/origin/*"

#: The namespace a branch lives in on a remote. `git ls-remote <url> main` is a *pattern*
#: match on slash boundaries, so it answers for `refs/tags/main` and for
#: `refs/heads/release/main` as readily as for the branch — `--heads` rules out the first
#: and comparing against this exact name rules out the second.
HEADS_NAMESPACE = "refs/heads/"
HEADS_ONLY = "--heads"

#: Ends git's option parsing. `url` and `default_branch` are typed by the Operator, and a
#: value beginning with `-` would otherwise be read as an option rather than an operand.
END_OF_OPTIONS = "--"

#: A `PATH` for the case where this process has none; `git` still has to be findable.
FALLBACK_PATH = "/usr/local/bin:/usr/bin:/bin"

#: What a clone leaves behind, and what `base_exists` looks for.
GIT_DIRECTORY = ".git"


def command_environment(askpass: Path, home: Path, token: str) -> dict[str, str]:
    """The whole environment a git command runs in. Nothing here is inherited but `PATH`.

    Built rather than copied so that no other secret this process holds can reach a hook, a
    helper or a filter that a git command starts.
    """
    return {
        # `.get(name, default)` would hand back the empty string when PATH is set but
        # empty, and every command would then fail to find `git` at all
        "PATH": os.environ.get("PATH") or FALLBACK_PATH,
        # a private, empty HOME: no user .gitconfig, no credential store, no url.insteadOf
        "HOME": str(home),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ASKPASS": str(askpass),
        ASKPASS_TOKEN_VAR: token,
    }


def tree_bytes(root: Path) -> int:
    """How much a clone wrote, reported by line 2 of the check."""
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def discard_partial_clone(dest: Path, *, existed: bool) -> None:
    """Remove what a failed clone left, and only that.

    A clone the timeout killed leaves a half-made directory behind. `base_exists` would then
    report it as a base clone, and every check after this one would fetch into something
    that is not a repository — with no path back, because a clone never runs again once a
    base is there.

    `existed` is why this is safe: a directory that was already there when the clone started
    is not this call's to delete. Deleting it would turn a failed clone into data loss, which
    is a worse outcome than the one being repaired.
    """
    if existed:
        return
    shutil.rmtree(dest, ignore_errors=True)


class SubprocessGit:
    """The `Git` port over `git(1)`."""

    def __init__(self, token: str, timeout_seconds: int = TIMEOUT_SECONDS) -> None:
        self._token = token
        self._timeout = timeout_seconds
        directory = Path(tempfile.mkdtemp(prefix="orchestrator-git-"))
        self._home = directory / "home"
        self._home.mkdir()
        self._askpass = directory / ASKPASS_NAME
        self._askpass.write_text((Path(__file__).parent / ASKPASS_NAME).read_text())
        self._askpass.chmod(ASKPASS_MODE)
        # one adapter, one private directory, removed when the adapter is — the process
        # builds one of these at start-up, but a test builds one per case
        self._cleanup = weakref.finalize(self, shutil.rmtree, directory, True)

    # ── the port ─────────────────────────────────────────────────────────────

    def ls_remote(self, url: str, ref: str | None = None) -> RemoteRef | None:
        """Ask the remote for `HEAD`, or for one exact branch. No answer is `None`.

        A branch query is `--heads` plus an equality test on the ref that came back, because
        the operand is a glob pattern to git rather than a name: without both, `main` is
        answered by `refs/tags/main` and by `refs/heads/release/main`.
        """
        if ref is None:
            return self._first(self._run("ls-remote", END_OF_OPTIONS, url, "HEAD"))
        wanted = f"{HEADS_NAMESPACE}{ref}"
        answer = self._run("ls-remote", HEADS_ONLY, END_OF_OPTIONS, url, ref)
        for candidate in self._refs(answer):
            if candidate.ref == wanted:
                return candidate
        return None

    @staticmethod
    def _refs(answer: str) -> list[RemoteRef]:
        """`ls-remote`'s output: one `sha\tref` per line."""
        refs = []
        for line in answer.splitlines():
            sha, _, name = line.partition("\t")
            if sha.strip() and name.strip():
                refs.append(RemoteRef(ref=name.strip(), sha=sha.strip()))
        return refs

    def _first(self, answer: str) -> RemoteRef | None:
        refs = self._refs(answer)
        return refs[0] if refs else None

    def base_exists(self, dest: Path) -> bool:
        return (dest / GIT_DIRECTORY).is_dir()

    def clone_base(self, url: str, dest: Path) -> CloneResult:
        """The blobless, un-checked-out base clone (AD-14).

        `--no-checkout` because nothing reads a worktree here — Epic 4 adds one per Story —
        and `--filter=blob:none` because the check needs the history and one file, not every
        blob that was ever committed. A server that does not offer filtering warns and sends
        everything, which is a slower clone rather than a failed one.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        existed = dest.exists()
        started = time.monotonic()
        try:
            self._run(
                "clone",
                "--no-checkout",
                "--filter=blob:none",
                END_OF_OPTIONS,
                url,
                str(dest),
            )
        except GitError:
            discard_partial_clone(dest, existed=existed)
            raise
        return CloneResult(seconds=time.monotonic() - started, bytes=tree_bytes(dest))

    def fetch_base(self, dest: Path, branch: str) -> None:
        """Bring every head up to date, then point HEAD at the branch a Run works from.

        No `--filter` here: a partial clone carries its filter in `remote.origin`, and
        passing one to a fetch in a clone that is *not* partial is an error rather than a
        no-op. HEAD is moved with `update-ref`, which touches no blob and needs no checkout.
        """
        self._run("-C", str(dest), "fetch", ORIGIN, REMOTE_REFSPEC)
        sha = self._attempt(
            "-C", str(dest), "rev-parse", "--verify", "--quiet", self._remote(branch)
        )
        if sha is not None:
            self._run("-C", str(dest), "update-ref", "HEAD", sha.strip())

    def branch_exists(self, dest: Path, branch: str) -> bool:
        rev = self._attempt(
            "-C", str(dest), "rev-parse", "--verify", "--quiet", self._remote(branch)
        )
        return rev is not None

    def read_file(self, dest: Path, ref: str, path: str) -> str | None:
        """One file's text at a ref, or `None` when the ref or the file is not there.

        The remote-tracking ref is preferred: a base clone is never checked out, so
        `origin/main` is what it holds and `main` may not exist as a local branch at all.
        """
        for candidate in (self._remote(ref), ref):
            text = self._attempt("-C", str(dest), "show", f"{candidate}:{path}")
            if text is not None:
                return text
        return None

    # ── running one command ──────────────────────────────────────────────────

    def _remote(self, branch: str) -> str:
        return f"{ORIGIN}/{branch}"

    def _command(self, arguments: tuple[str, ...]) -> list[str]:
        """`credential.helper=` clears any helper a config this adapter did not read names."""
        return ["git", "-c", "credential.helper=", *arguments]

    def _run(self, *arguments: str) -> str:
        """One git command. A non-zero exit and a timeout are both a redacted `GitError`."""
        command = self._command(arguments)
        shown = redact(" ".join(command), self._token)
        try:
            completed = subprocess.run(  # fixed argv, no shell
                command,
                env=command_environment(self._askpass, self._home, self._token),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise GitError(
                command=shown,
                exit_code=TIMEOUT_EXIT_CODE,
                output=f"timeout after {self._timeout} s",
            ) from error
        if completed.returncode != 0:
            raise GitError(
                command=shown,
                exit_code=completed.returncode,
                output=redact(
                    (completed.stdout + completed.stderr).strip() or "no output", self._token
                ),
            )
        return completed.stdout

    def _attempt(self, *arguments: str) -> str | None:
        """The same command, where a non-zero exit means "not there" rather than "broken".

        A timeout still raises: a command that never finished says nothing about whether the
        ref or the file exists, and reporting it as absent would be a guess.
        """
        try:
            return self._run(*arguments)
        except GitError as error:
            if error.exit_code == TIMEOUT_EXIT_CODE:
                raise
            return None
