"""ch-bsd T0.2 r1 S2 (L169): a GRANDCHILD of the session whose argv is exactly the resource
tracker's (`python -c "from multiprocessing.resource_tracker import main;main(<fd>)"`). It runs
the real tracker main on a pipe it also holds the write end of, so it never sees EOF and does
not end with anyone. Its parent is a plain child left running, not this session, so it is not
the exempt process: the reaper must report and stop it, and the session fails."""
import os
import subprocess
import sys

from suite_health_support import report

_MID = r"""
import os, subprocess, sys
r, w = int(sys.argv[1]), int(sys.argv[2])
gc = subprocess.Popen([sys.executable, "-c",
                       "from multiprocessing.resource_tracker import main;main(%d)" % r],
                      pass_fds=(r, w))
print(gc.pid, flush=True)
import time
time.sleep(600)
"""


def test_a_grandchild_carries_the_trackers_argv():
    r, w = os.pipe()
    mid = subprocess.Popen([sys.executable, "-c", _MID, str(r), str(w)], pass_fds=(r, w),
                           stdout=subprocess.PIPE, text=True)
    os.close(r)
    os.close(w)
    gc = int(mid.stdout.readline())
    report(pid=gc, mid=mid.pid)
    assert gc > 0
