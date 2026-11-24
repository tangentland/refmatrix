"""task-29.4a fixture (AC-2): a passing test that starts a child process, so `tier_of` puts the
file in run tier `daemon` by its process signal."""
import subprocess
import sys


def test_passes_with_a_child():
    subprocess.run([sys.executable, "-c", "pass"], check=True)
