from cldv_si2_collectors import _latest_two


def test_latest_two_picks_two_newest():
    y0, v0, y1, v1 = _latest_two({2022: 1.0, 2023: 2.0, 2024: 3.0})
    assert (y0, v0, y1, v1) == (2024, 3.0, 2023, 2.0)


def test_latest_two_single_year():
    y0, v0, y1, v1 = _latest_two({2024: 5.0})
    assert (y0, v0) == (2024, 5.0)
    assert y1 is None and v1 is None


def test_latest_two_empty():
    assert _latest_two({}) == (None, None, None, None)


def test_crossover_direction():
    # falling ratio (cognitive shrinking vs AI-adjacent) => negative YoY
    cog = {2023: 110.0, 2024: 100.0}     # clerical down
    ai = {2023: 100.0, 2024: 120.0}      # professionals up
    ratio = {y: cog[y] / ai[y] for y in (2023, 2024)}
    yoy = (ratio[2024] - ratio[2023]) / ratio[2023] * 100
    assert yoy < 0     # inverted in scoring -> higher displacement
