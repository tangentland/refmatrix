"""task-29.4a fixture (AC-12): the touch is made by a CHILD the test spawned, and the test
ignores the child's exit code (86, `rmx_sandbox.CHILD_EXIT`). The conftest's child-touch check
must still fail the test at teardown, and the runner must fail the run. Same target as
case_live_touch.py."""
import os
import pwd
import subprocess
import sys

TARGET = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".refmatrix", "rmx-294a-ac12-probe")


def test_child_touches_a_live_path():
    subprocess.run([sys.executable, "-c", f"open({TARGET!r}, 'rb')"], check=False)
