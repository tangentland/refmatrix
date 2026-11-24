"""task-29.4a fixture (AC-2, AC-9): a test that PASSES and then errors at teardown, bug-230's
shape ("read every ERROR as well as every FAILED")."""
import pytest


@pytest.fixture
def breaks_on_teardown():
    yield
    raise RuntimeError("fixture: teardown broke after a passing test")


def test_passes_then_errors_at_teardown(breaks_on_teardown):
    assert True
