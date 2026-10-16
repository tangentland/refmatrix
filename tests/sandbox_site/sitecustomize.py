"""Task 23.0 R4: every child a sandboxed test spawns refuses live paths ITSELF.

bug-088's recorder patched `socket.socket.connect` inside the pytest process and could not see
a spawned `rmx` at all. The conftest puts this directory first on the children's `PYTHONPATH`
(and the spawn audit hook re-adds it to an env a test built by hand), so CPython's `site`
imports this module in every child interpreter and the child installs the SAME audit hook,
over the SAME deny set (`$RMX_SANDBOX_ROOT/deny.json`), before any of its own code runs. A
violation writes the touches log, prints `SandboxViolation: ...` to stderr and exits 86.

A child started with `-I`, `-E` or `-S` never reaches this file; task 23.0's implementation
summary lists the spawn sites that do (none in `src/` or `tests/` at b86809a).
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import rmx_sandbox  # noqa: E402

rmx_sandbox.install_from_env()
