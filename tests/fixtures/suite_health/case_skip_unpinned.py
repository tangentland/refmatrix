"""task-29.4a fixture (AC-2): a skip nobody pinned, so the inner session's SkipGate fails it."""
import pytest


def test_skips_unpinned():
    pytest.skip("fixture: an unpinned skip")
