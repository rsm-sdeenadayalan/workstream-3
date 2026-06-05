from cldv_si1_llm import _parse as _parse_scorer


def test_scorer_parse_includes_evidence():
    out = ('{"displacement_score": 0.5, "ai_attributed": true, '
           '"summary": "cutting ops headcount via automation", '
           '"evidence": "we reduced headcount through automation"}')
    r = _parse_scorer(out)
    assert r["score"] == 0.5
    assert r["ai"] is True
    assert r["evidence"] == "we reduced headcount through automation"


def test_scorer_parse_missing_evidence_defaults_empty():
    out = '{"displacement_score": 0.0, "ai_attributed": false, "summary": "neutral"}'
    r = _parse_scorer(out)
    assert r["evidence"] == ""


from cldv_si1_judge import _parse_judge


def test_parse_judge_valid():
    out = '{"judge_score": 0.6, "justified": true, "rationale": "explicit AI headcount cut"}'
    r = _parse_judge(out)
    assert r["score"] == 0.6
    assert r["justified"] is True
    assert "AI" in r["rationale"]


def test_parse_judge_clamps_range():
    assert _parse_judge('{"judge_score": 2.5, "justified": false}')["score"] == 1.0
    assert _parse_judge('{"judge_score": -9, "justified": false}')["score"] == -1.0


def test_parse_judge_embedded_in_prose():
    r = _parse_judge('Here:\n{"judge_score": 0.0, "justified": true}\nthanks')
    assert r["score"] == 0.0 and r["justified"] is True


def test_parse_judge_rejects_garbage():
    assert _parse_judge("no json here") is None
    assert _parse_judge('{"justified": true}') is None   # missing judge_score
    assert _parse_judge("") is None


def test_parse_judge_rejects_nonnumeric_score():
    assert _parse_judge('{"judge_score": "abc", "justified": true}') is None
    assert _parse_judge('{"judge_score": null, "justified": true}') is None


from cldv_si1_validate import judge_concordance


def test_judge_concordance_full_agreement():
    # both rows: scorer & judge same direction; both justified
    rows = [(0.6, 0.5, True), (-0.4, -0.3, True)]
    conc, jrate, n = judge_concordance(rows)
    assert conc == 1.0 and jrate == 1.0 and n == 2


def test_judge_concordance_split():
    rows = [(0.6, -0.6, False), (0.5, 0.5, True)]   # disagree+unjustified, agree+justified
    conc, jrate, n = judge_concordance(rows)
    assert conc == 0.5 and jrate == 0.5 and n == 2


def test_judge_concordance_skips_unjudged_rows():
    rows = [(0.6, None, None), (0.5, 0.5, True)]     # first has no judge verdict
    conc, jrate, n = judge_concordance(rows)
    assert n == 1 and conc == 1.0 and jrate == 1.0
