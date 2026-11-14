"""The ONE reader of this process's working directory.

Why (bug-212 r1, ch-bsd finding s-1, 2026-11-11): a backgrounded post-commit `rmx sync`
outlived `git worktree remove`, and `Path.cwd()` raised a raw `FileNotFoundError` traceback on
the committing terminal. The first fix guarded cli.py only; the auditor then set
`REFMATRIX_ROOT` -- the remedy that fix's own error text recommends -- and walked straight into
the same traceback one module over (`discovery.partition_marker`). `discovery`, `sync`, `mcp`
and `cctree` each read the cwd raw. So every cwd read goes through `current_dir()` here, and a
vanished cwd is ONE named error everywhere: `WorkingDirectoryGone`, which the CLI's group
turns into a single `Error:` line (exit 1) and the MCP dispatcher into an `isError` reply that
says what happened.

Stdlib only: `cctree` imports this, and `cctree` must stay importable without third-party
packages (the hub renders trees on a host without the dense extra).
"""
from __future__ import annotations

import os  # $PWD and REFMATRIX_ROOT for the message
from pathlib import Path


class WorkingDirectoryGone(RuntimeError):
    """This process's working directory no longer exists (`os.getcwd()` failed with ENOENT).

    NOT an OSError on purpose (bug-212 r1, 2026-11-11): a bare `FileNotFoundError` with no
    filename names nothing, and every `except OSError` on the way up (a missing file, a socket
    that went away) would read it as something else. A RuntimeError, so a handler that already
    turns `RuntimeError` into a clean `Error:` line (the CLI's daemon-down `--since` branch)
    keeps doing so."""

    def __init__(self, remedy: "str | None" = None) -> None:
        super().__init__(cwd_gone_message(remedy))


def cwd_gone_message(remedy: "str | None" = None) -> str:
    """The one wording of "this process's working directory no longer exists".

    `$PWD` is the shell's record of the dir it `cd`ed into -- the kernel cannot name a deleted
    cwd -- so it is quoted as the shell's claim, or said to be unknown. The remedy depends on
    what is already set (ch-bsd r1 impression "an error message's remedy is a test case"): with
    `REFMATRIX_ROOT` unset, setting it is a remedy; with it set, the command still read the
    working directory (to resolve the partition or the project root), so the only remedy is a
    directory that exists -- telling the user to set what they already set would send them in
    a circle. A reader whose remedy is something else (`cctree`'s `--project`, a library
    caller's `project_root`) passes its own `remedy`, for the same reason."""
    where = os.environ.get("PWD") or "(unknown: $PWD is unset)"
    if not remedy:
        remedy = ("cd to an existing project directory (REFMATRIX_ROOT is set, but this "
                  "command also reads the working directory)"
                  if os.environ.get("REFMATRIX_ROOT")
                  else "cd to a project, or set REFMATRIX_ROOT")
    return f"the working directory no longer exists ({where}); {remedy}"


def current_dir(remedy: "str | None" = None) -> Path:
    """`Path.cwd()`, or `WorkingDirectoryGone` when the working directory was deleted.

    Only the cwd read's own ENOENT is translated -- the `try` holds nothing else, so a missing
    FILE elsewhere can never be reported as a missing cwd. Any other failure of the read (an
    unreadable parent, EACCES) is a different condition and propagates as itself. It calls
    `Path.cwd()` (not `os.getcwd()`) so a test that stands a `Path.cwd` in for a cwd still
    reaches every reader through here."""
    try:
        return Path.cwd()
    except FileNotFoundError as exc:
        raise WorkingDirectoryGone(remedy) from exc
