from cldv_si1_score import aggregate_rows, velocity_for_country


def test_employment_weighted_aggregate():
    # US Q1: JPM(emp 310000, proxy 0.2), Goldman(emp 46000, proxy 0.6)
    rows = [
        ("US", "2026Q1", 0.2, 0.1, 310000),
        ("US", "2026Q1", 0.6, 0.2, 46000),
    ]
    agg = aggregate_rows(rows)
    expected = (0.2 * 310000 + 0.6 * 46000) / (310000 + 46000)
    assert abs(agg["US"]["2026Q1"]["proxy"] - expected) < 1e-9
    assert agg["US"]["2026Q1"]["n"] == 2


def test_velocity_is_latest_minus_prev():
    rows = [
        ("US", "2026Q1", 0.2, 0.0, 100000),
        ("US", "2026Q1", 0.6, 0.0, 100000),   # Q1 weighted = 0.4
        ("US", "2026Q2", 0.5, 0.0, 100000),
        ("US", "2026Q2", 0.7, 0.0, 100000),   # Q2 weighted = 0.6
    ]
    agg = aggregate_rows(rows)
    v = velocity_for_country(agg["US"])
    assert v["latest"] == "2026Q2"
    assert abs(v["level_proxy"] - 0.6) < 1e-9
    assert abs(v["velocity"] - (0.6 - 0.4)) < 1e-9     # +0.2 accelerating


def test_single_quarter_has_no_velocity():
    agg = aggregate_rows([("IN", "2026Q1", 0.3, 0.1, 50000)])
    v = velocity_for_country(agg["IN"])
    assert v["velocity"] is None
    assert v["level_proxy"] == 0.3


def test_none_proxy_rows_ignored():
    agg = aggregate_rows([("BR", "2026Q1", None, None, 1000),
                          ("BR", "2026Q1", 0.5, 0.0, 1000)])
    assert abs(agg["BR"]["2026Q1"]["proxy"] - 0.5) < 1e-9
    assert agg["BR"]["2026Q1"]["n"] == 1
