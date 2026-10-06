"""The learning toggle: one resolver for "may this process teach the graph?".

`rmx grep` has always had `--learn/--no-learn`, which governs ONE invocation.
That is not enough to turn the grep→graph loop off, because two of the things
that learn never see a shell flag:

  * the DAEMON drains the learn queue on its own tick, in a process started
    minutes or days earlier;
  * the PreToolUse rewrite hook spawns `rmx grep` itself, so whatever the
    operator typed is not on that command line.

So the state has to outlive a process, and four call sites must read it the
same way. Four sites growing their own env check is the shape of
`feedback_reuse_shared_stoplist` (one junk-token defect, four copies) and of
`feedback_check_the_sibling_condition` (a gate fixed on one of its conditions)
— hence ONE function, imported by `cli.py`, `daemon.py` and `search_hooks.py`.

WHY A MARKER FILE AND NOT A CONFIG KEY. The two callers that most need the
answer cannot open the catalog: the rewrite hook answers it with a `[ -f ]`
test on the path of every bare grep in every session (a DuckDB attach there
would be a per-tool-call tax), and a CLI whose daemon is down has no reader at
all. A file is also the only form an operator can flip without a running
daemon — which is exactly the state a stuck learn loop leaves behind.

This module imports nothing from refmatrix and opens nothing. That is a
tested property (`tests/test_learn_switch.py`), not a convention.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The marker's NAME is the same at both scopes; only its directory differs.
MARKER_NAME = "learn.off"

ENV_VAR = "RMX_LEARN"

_OFF_VALUES = frozenset({"0", "off", "false", "no"})
_ON_VALUES = frozenset({"1", "on", "true", "yes"})

# The rules, in the order they are consulted. `rmx learn status` prints the one
# that decided, because "learning is off" is not actionable on its own — the
# operator needs to know WHICH of three places to go and change.
RULES = ("env", "store-marker", "global-marker", "default")


@dataclass(frozen=True)
class Decision:
    """The answer AND its provenance.

    `rejected_env` carries a malformed `RMX_LEARN` value verbatim. A typo must
    not read as either answer: `RMX_LEARN=banana` falls through to the next
    rule, and the rejected text travels with the decision so a surface can show
    the operator their mistake instead of a toggle that looks on while they
    believe they turned it off (CLAUDE.md#no-silent-failures).
    """
    enabled: bool
    rule: str
    rejected_env: str | None = None


def global_marker() -> Path:
    """The user-level marker: `~/.refmatrix/learn.off`."""
    return Path.home() / ".refmatrix" / MARKER_NAME


def store_marker(root: "str | os.PathLike") -> Path:
    """The per-store marker: `<store root>/learn.off`."""
    return Path(root) / MARKER_NAME


def _env_value() -> "tuple[bool | None, str | None]":
    """(decision, rejected_text). Both None means the variable is unset."""
    raw = os.environ.get(ENV_VAR)
    if raw is None:
        return (None, None)
    val = raw.strip().lower()
    if val in _OFF_VALUES:
        return (False, None)
    if val in _ON_VALUES:
        return (True, None)
    return (None, raw)


def decision(root: "str | os.PathLike | None" = None) -> Decision:
    """Resolve the toggle and say which rule decided it.

    Order: env, then the per-store marker, then the global marker, then the
    shipped default (ON — this switch does not change what rmx does out of the
    box). The env wins so a single command can opt back IN without the operator
    deleting their own marker.
    """
    env_enabled, rejected = _env_value()
    if env_enabled is not None:
        return Decision(env_enabled, "env", rejected)
    if root is not None:
        try:
            if store_marker(root).exists():
                return Decision(False, "store-marker", rejected)
        except OSError:
            # An unreadable store dir is not an answer; fall through to the
            # scope that is readable rather than inventing one.
            pass
    try:
        if global_marker().exists():
            return Decision(False, "global-marker", rejected)
    except OSError:
        pass
    return Decision(True, "default", rejected)


def learning_enabled(root: "str | os.PathLike | None" = None) -> bool:
    """May this process teach the graph? The one predicate every site calls."""
    return decision(root).enabled


def set_enabled(root: "str | os.PathLike | None", on: bool, *,
                scope: str = "store") -> Path:
    """Write (or clear) the marker for one scope. Returns the marker path.

    The scopes are INDEPENDENT: turning learning on at store scope removes the
    store marker and leaves a global one alone, so a project cannot silently
    undo a machine-wide setting. `decision()` still reports OFF in that case and
    names `global-marker` as the reason.
    """
    if scope not in ("store", "global"):
        raise ValueError(f"scope must be 'store' or 'global', got {scope!r}")
    if scope == "store":
        if root is None:
            raise ValueError("store scope needs a store root")
        marker = store_marker(root)
    else:
        marker = global_marker()
    if on:
        marker.unlink(missing_ok=True)
        return marker
    marker.parent.mkdir(parents=True, exist_ok=True)
    # The body is for a human reading the file, never parsed: existence is the
    # signal, so a truncated or empty file still means off.
    marker.write_text(
        "off\n"
        "# rmx learning is DISABLED for this scope.\n"
        f"# Written by `rmx learn off`. Remove this file (or `rmx learn on`)\n"
        "# to let `rmx grep` teach the graph again.\n"
    )
    return marker
