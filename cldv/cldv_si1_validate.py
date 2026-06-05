"""SI1 validation - automated LLM-as-judge concordance (replaces the spec's
human 2-reviewer step).

  concordance -> scorer-vs-judge directional concordance + justified-rate across
                 all judged transcripts; target >= 80%. This is the published
                 accuracy metric for SI1 and the gate in cldv_verify.
  agree       -> keyword-vs-Claude directional agreement (a first-pass signal:
                 quantifies how much contextual scoring changes vs naive keyword
                 counting).

Usage:
  python cldv/cldv_si1_validate.py concordance
  python cldv/cldv_si1_validate.py agree
"""
import sys

from cldv_db import get_conn

_NEUTRAL_BAND = 0.1
_MIN_CONCORDANCE = 0.80


def label(score):
    if score is None:
        return ""
    s = float(score)
    if s > _NEUTRAL_BAND:
        return "displacement"
    if s < -_NEUTRAL_BAND:
        return "augmentation"
    return "neutral"


def _concordance(pairs):
    if not pairs:
        return 0.0, 0
    agree = sum(1 for a, b in pairs if a == b)
    return agree / len(pairs), len(pairs)


def judge_concordance(rows):
    """Pure: rows of (scorer_score, judge_score, justified) ->
    (directional_concordance, justified_rate, n_judged). Rows without a judge
    score are ignored."""
    judged = [(s, j, x) for s, j, x in rows if s is not None and j is not None]
    pairs = [(label(s), label(j)) for s, j, _ in judged]
    conc, n = _concordance(pairs)
    jrate = (sum(1 for _, _, x in judged if x) / len(judged)) if judged else 0.0
    return conc, jrate, n


def concordance():
    """Scorer-vs-judge concordance over all judged transcripts (the SI1 accuracy
    metric that replaces the human pass)."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT llm_score, judge_score, judge_justified "
                    "FROM cldv_si1_company_scores WHERE judge_score IS NOT NULL")
        rows = cur.fetchall()
    conn.close()
    conc, jrate, n = judge_concordance(rows)
    verdict = "PASS" if conc >= _MIN_CONCORDANCE else f"BELOW {_MIN_CONCORDANCE*100:.0f}%"
    print(f"judged transcripts: {n}")
    print(f"  scorer vs judge directional concordance: {conc*100:.1f}%  ({verdict})")
    print(f"  scorer score justified by its evidence:  {jrate*100:.1f}%")


def agree():
    """Automated keyword-vs-Claude directional agreement (no humans)."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT proxy_score, llm_score FROM cldv_si1_company_scores "
                    "WHERE proxy_score IS NOT NULL AND llm_score IS NOT NULL")
        rows = cur.fetchall()
    conn.close()
    pairs = [(label(p), label(l)) for p, l in rows]
    a, n = _concordance(pairs)
    print(f"keyword vs Claude directional agreement: {a*100:.1f}% over {n} transcripts")
    print("(low agreement is expected - it quantifies how much contextual scoring "
          "changes vs naive keyword counting)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "concordance"
    if cmd == "agree":
        agree()
    else:
        concordance()
