"""AC-5 case 4, second half: the NEXT inner session after a killed run. Nothing here starts a
process; its session start must find the killed run's orphan and stop it, without failing."""


def test_nothing():
    assert True
