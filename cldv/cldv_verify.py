"""Post-run QA gate for the CLDV pipeline.

Runs integrity + quality checks against the `cldv` database and exits non-zero
on any hard FAIL so it can gate CI / a publish step. FAILs are structural
(weights, score ranges, provenance); WARNs are data-quality signals worth a human
look (coverage gaps, outliers) that do not block.

Usage:  python cldv/cldv_verify.py        (exit 0 = pass/warn, 1 = fail)
"""
import sys

from cldv_db import COUNTRIES, get_conn

_FAILS = []
_WARNS = []


def _fail(msg):
    _FAILS.append(msg)


def _warn(msg):
    _WARNS.append(msg)


def check_weights(cur):
    cur.execute("SELECT COALESCE(SUM(weight), 0) FROM cldv_subindex_weights")
    s = float(cur.fetchone()[0])
    if abs(s - 1.0) > 1e-6:
        _fail(f"sub-index weights sum to {s:.4f}, expected 1.0")
    cur.execute("SELECT sub_index, COALESCE(SUM(weight),0) FROM cldv_score_methodology "
                "WHERE scored GROUP BY sub_index")
    for si, w in cur.fetchall():
        if abs(float(w) - 1.0) > 1e-6:
            _fail(f"{si} scored-metric weights sum to {float(w):.4f}, expected 1.0")


def check_provenance(cur):
    # every scored SI2/SI3 metric must carry a working source_url
    cur.execute(
        "SELECT sub_index, metric_key, country_iso FROM cldv_raw_metrics m "
        "WHERE sub_index IN ('SI2','SI3') AND source_url IS NULL "
        "AND metric_key IN (SELECT metric_key FROM cldv_score_methodology WHERE scored)")
    miss = cur.fetchall()
    if miss:
        _fail(f"{len(miss)} scored SI2/SI3 metrics missing source_url (e.g. {miss[0]})")
    # SI1 scored metrics must have either a source_url or lineage in raw_value
    cur.execute("SELECT country_iso FROM cldv_raw_metrics "
                "WHERE sub_index='SI1' AND metric_key='corporate_displacement_velocity' "
                "AND source_url IS NULL AND raw_value IS NULL")
    if cur.fetchall():
        _fail("SI1 velocity metric without provenance (no source_url and no lineage)")


def check_scores(cur):
    cur.execute("SELECT run_id FROM cldv_score_final ORDER BY scored_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        _fail("no rows in cldv_score_final")
        return
    run_id = row[0]
    cur.execute("SELECT country_iso, cldv_score, rank FROM cldv_score_final WHERE run_id=%s",
                (run_id,))
    rows = cur.fetchall()
    ranks = sorted(r[2] for r in rows)
    if ranks != list(range(1, len(rows) + 1)):
        _fail(f"ranks not contiguous 1..n: {ranks}")
    for iso, score, _ in rows:
        if score is None or not (0 <= float(score) <= 100):
            _fail(f"{iso} CLDV score out of [0,100]: {score}")


def check_coverage(cur):
    for si in ("SI1", "SI2", "SI3"):
        cur.execute("SELECT COUNT(DISTINCT country_iso) FROM cldv_raw_metrics WHERE sub_index=%s",
                    (si,))
        n = cur.fetchone()[0]
        if n < len(COUNTRIES):
            _warn(f"{si}: data for only {n}/{len(COUNTRIES)} countries")


def check_outliers(cur):
    cur.execute("SELECT sub_index, country_iso, metric_key, metric_value "
                "FROM cldv_raw_metrics WHERE unit IN ('pct_yoy','qoq_delta') "
                "AND ABS(metric_value) > 50")
    for si, iso, mk, v in cur.fetchall():
        _warn(f"outlier {si} {iso} {mk} = {v} (|YoY| > 50%) - verify source")


def check_llm_coverage(cur):
    cur.execute("SELECT COUNT(*), COUNT(llm_score) FROM cldv_si1_company_scores")
    total, scored = cur.fetchone()
    if total and scored < total:
        _warn(f"SI1: {scored}/{total} transcripts have a Claude contextual score "
              f"({total - scored} on keyword fallback)")


_JUDGE_MIN_CONCORDANCE = 0.80


def check_judge_concordance(cur):
    """SI1 accuracy gate: an independent judge must agree with the scorer on
    direction >= 80% (replaces the human 2-reviewer pass). FAIL below threshold;
    WARN when judge coverage is incomplete."""
    from cldv_si1_validate import judge_concordance
    cur.execute("SELECT COUNT(llm_score), COUNT(judge_score) FROM cldv_si1_company_scores")
    scored, judged = cur.fetchone()
    if not scored:
        return
    if judged < scored:
        _warn(f"SI1: {judged}/{scored} Claude-scored transcripts have a judge verdict")
    if judged:
        cur.execute("SELECT llm_score, judge_score, judge_justified "
                    "FROM cldv_si1_company_scores WHERE judge_score IS NOT NULL")
        conc, jrate, n = judge_concordance(cur.fetchall())
        if conc < _JUDGE_MIN_CONCORDANCE:
            _fail(f"SI1 scorer-vs-judge concordance {conc*100:.1f}% < "
                  f"{_JUDGE_MIN_CONCORDANCE*100:.0f}% over {n} judged rows")
        else:
            _warn(f"SI1 scorer-vs-judge concordance {conc*100:.1f}% "
                  f"(justified {jrate*100:.1f}%, {n} rows)")


def run_verify() -> int:
    """Run all checks; print results; return process exit code (0 ok, 1 fail)."""
    _FAILS.clear()
    _WARNS.clear()
    conn = get_conn()
    with conn.cursor() as cur:
        check_weights(cur)
        check_provenance(cur)
        check_scores(cur)
        check_coverage(cur)
        check_outliers(cur)
        check_llm_coverage(cur)
        check_judge_concordance(cur)
    conn.close()
    for w in _WARNS:
        print(f"  WARN  {w}")
    for f in _FAILS:
        print(f"  FAIL  {f}")
    if _FAILS:
        print(f"\nVERIFY: FAILED ({len(_FAILS)} fail, {len(_WARNS)} warn)")
        return 1
    print(f"\nVERIFY: PASSED ({len(_WARNS)} warn)")
    return 0


if __name__ == "__main__":
    sys.exit(run_verify())
