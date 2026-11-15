"""Ruling L154; ch-bsd T0.2 r1 S2 (L169): the REAL stdlib multiprocessing resource tracker,
started as a direct child of this session, the way loading torch starts it. It is the one
exempt process: it ignores SIGTERM and ends when its parent closes the pipe at exit."""
from multiprocessing import resource_tracker

from suite_health_support import report


def test_starts_the_stdlib_resource_tracker():
    resource_tracker.ensure_running()
    pid = resource_tracker._resource_tracker._pid
    report(pid=pid)
    assert pid
