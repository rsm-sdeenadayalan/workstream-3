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
