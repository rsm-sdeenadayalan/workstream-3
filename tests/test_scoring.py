from cldv_scoring import _minmax


def test_minmax_0_100():
    out = _minmax({"US": 10, "IN": 20, "BR": 30})
    assert out["US"] == 0.0 and out["BR"] == 100.0
    assert abs(out["IN"] - 50.0) < 1e-9


def test_minmax_invert():
    out = _minmax({"US": 10, "BR": 30}, invert=True)
    assert out["US"] == 100.0 and out["BR"] == 0.0


def test_minmax_all_equal_is_50():
    out = _minmax({"A": 5, "B": 5, "C": 5})
    assert all(v == 50.0 for v in out.values())


def test_minmax_ignores_none():
    out = _minmax({"A": None, "B": 10, "C": 20})
    assert "A" not in out
    assert out["B"] == 0.0 and out["C"] == 100.0
