"""THE parse of a numeric (seconds) env knob: one leaf module, stdlib only.

Why a leaf (task 3.7 remedy r6, ch-bsd 3.7 r6 #m-1, 2026-11-09): r5 put `env_float` in
`modelsrv`, but `modelsrv` imports `subproc`, so `subproc.DEFAULT_TIMEOUT_S`
(`RMX_WORKER_TIMEOUT_S`) could not use it without an import cycle and stayed a bare
`float(os.environ.get(...))`. Measured by the audit (`bsd-r6-probe-import-env.log`,
`bsd-r6-probe-worker-timeout-typo.log`): `RMX_WORKER_TIMEOUT_S=300s` made
`import refmatrix.modelsrv` raise, so every daemonless `shared_embedder` call raised
(4/4 calls, 0 loads); `RMX_ADOPT_GRACE_S=20s`, `RMX_HEARTBEAT_S=5s`,
`RMX_HUB_HEARTBEAT_STALE_S=60s` and `RMX_LEARN_DRAIN_BUDGET_S=5s` each made
`import refmatrix.daemon` raise; `RMX_WORKER_IDLE_S=300s` was swallowed with NO warning and
silently disabled the hub's idle reaping. This module imports nothing from `refmatrix`, so
every module on those import paths (`subproc`, `modelsrv`, `daemon`) can share it.
"""
from __future__ import annotations

import logging
import math
import os
import threading

# (name, raw value) pairs already warned for, process-wide. `modelsrv._ENV_WARNED` is this
# same set object (its `env_float` binding passes it), so a value is warned once no matter
# which module read it.
_ENV_WARNED: "set[tuple[str, str]]" = set()
_ENV_WARNED_LOCK = threading.Lock()


def env_float(name: str, default: float, *, logger: "str | None" = None,
              warned: "set[tuple[str, str]] | None" = None) -> float:
    """The env value of `name` as a float, else `default`. Unset or empty is the default,
    silently. A value that is not a finite, non-negative number (an operator typo: `300s`,
    `30m`, `nan`, `-5`) is ALSO the default, with ONE WARNING per process per
    `(name, value)` naming the variable and the value -- never a `ValueError` out of an
    import or a request path, and never a silent fallback.

    `logger` names the logger the warning goes to (the reading module, so an operator sees
    who read it); default this module's. `warned` is the dedupe set; default the
    process-wide `_ENV_WARNED`. Once per `(name, value)` because some knobs are re-read per
    call (`recall._reprobe_window`) to honour a changed env, and must not flood the log."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return float(default)
    try:
        value = float(raw)
    except ValueError:
        value = None
    if value is not None and math.isfinite(value) and value >= 0.0:
        return value
    seen = _ENV_WARNED if warned is None else warned
    key = (name, raw)
    with _ENV_WARNED_LOCK:
        first = key not in seen
        seen.add(key)
    if first:
        logging.getLogger(logger or __name__).warning(
            "%s=%r is not a finite non-negative number of seconds; using the default %s "
            "(said once per process)", name, raw, float(default))
    return float(default)
