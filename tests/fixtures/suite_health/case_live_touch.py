"""task-29.4a fixture (AC-12): a test that touches a deny-set target IN-PROCESS, without the
`sandbox_probe` marker. The target is a path under the account's real `~/.refmatrix/`, which
`rmx_sandbox.build_deny` always denies; the name does not exist, so even an unrefused open
touches nothing (it would raise FileNotFoundError, and the AC-12 test would still be red,
because `summary.txt` would then not name the target as a refused touch).

The home is read from the password database, not from the sandbox's real-home variable, so the
file carries no devtree signal and `tier_of` gives it run tier `unit`."""
import os
import pwd

TARGET = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".refmatrix", "rmx-294a-ac12-probe")


def test_touches_a_live_path():
    with open(TARGET, "rb"):
        pass
