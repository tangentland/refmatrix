"""task-29.4a fixture (AC-3): one test per row of task-29.4 `#r2-outcomes`, so the conftest's
`outcomes.jsonl` record can be checked against the normalisation table."""
import pytest


def test_passes():
    assert True


def test_skips():
    pytest.skip("fixture: an unpinned skip")


@pytest.mark.xfail(strict=True, reason="fixture: expected to fail, and does")
def test_strict_xfail_that_fails():
    assert False


@pytest.mark.xfail(strict=False, reason="fixture: non-strict, passes anyway")
def test_nonstrict_xfail_that_passes():
    assert True


@pytest.mark.xfail(strict=True, reason="fixture: strict, passes, so it is a failure")
def test_strict_xfail_that_passes():
    assert True


def test_fails():
    assert 1 == 2, "fixture: a plain failure"


@pytest.fixture
def breaks_on_teardown():
    yield
    raise RuntimeError("fixture: teardown broke after a passing test")


def test_errors_at_teardown(breaks_on_teardown):
    assert True
