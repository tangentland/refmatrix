"""AC-5 case 3: a ledger line naming a live, UNRELATED process with a different start time.

The outer test started the unrelated process (`$RMX_CASE_TARGET_PID`) before this session. This
case starts a Python child of its own, waits for that child's own ledger line, stops the child,
and rewrites ONLY the `pid` of that line to the unrelated pid. The line then carries the dead
child's start time (whatever form the ledger records it in), which is not the unrelated
process's: a reused pid. The reaper must not signal it, and must say so."""
import json
import os
import subprocess
import sys
import time

from suite_health_support import ledger_path, report

# How long the ledger line of a just-started child may take to appear: a hang guard for this
# fixture, not a bound under test.
_LEDGER_WAIT_S = 60.0


def test_points_a_ledger_line_at_an_unrelated_pid():
    target = int(os.environ["RMX_CASE_TARGET_PID"])
    ledger = ledger_path()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    line = None
    try:
        deadline = time.monotonic() + _LEDGER_WAIT_S
        while line is None and time.monotonic() < deadline:
            if ledger.is_file():
                for ln in ledger.read_text().splitlines():
                    try:
                        rec = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(rec, dict) and rec.get("pid") == child.pid:
                        line = ln
                        break
            if line is None:
                time.sleep(0.1)
    finally:
        child.kill()
        child.wait()
    assert line is not None, (
        f"no ledger line with pid={child.pid} in {ledger}: the spawn ledger "
        "(<sandbox root>/children.jsonl, task-29.4 #r4 item 1) was not written by the child")
    rec = json.loads(line)
    rec["pid"] = target
    text = ledger.read_text()
    ledger.write_text(text.replace(line, json.dumps(rec), 1))
    report(target=target, child=child.pid)
