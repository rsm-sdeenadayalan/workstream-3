from cldv_si1_headcount import parse_headcount, _extract_headcount


def test_parse_headcount_picks_latest_dated():
    ans = ("As of December 31, 2025, JPMorgan Chase employed 318,512 people. "
           "This is up from 317,233 at the end of 2024.")
    r = parse_headcount(ans)
    assert r["employees"] == 318512
    assert r["as_of"] == "2025-12-01"


def test_parse_headcount_no_number():
    assert parse_headcount("No figures were disclosed this period.") is None


def test_extract_headcount_from_filing_text():
    text = ("Human Capital. As of December 31, 2025 we had approximately "
            "318,512 employees worldwide.")
    assert _extract_headcount(text) == 318512


def test_extract_headcount_ignores_small_noise():
    # year-like and tiny numbers below the 5,000 floor are not headcounts
    assert _extract_headcount("in 2014 we hired 200 people") is None
