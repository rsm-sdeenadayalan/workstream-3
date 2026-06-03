"""SI1 aggregation + scoring.

transcripts (cldv_transcripts)
  → per-company-quarter NLP score (two-track, TF-IDF corpus weighting)
  → employment-weighted country-quarter aggregate
  → QoQ change = displacement VELOCITY  (the scored SI1 metric, per spec)
  → written to cldv_raw_metrics for the final scorer.

Public entry point: run_si1_scoring(conn, run_id) -> dict
"""
from datetime import date

from cldv_db import (COUNTRIES, CONFIDENCE, make_metric_result,
                     store_metric_datapoint, open_gap)
from cldv_si1_companies import employees_for
from cldv_si1_nlp import score_corpus

_Q_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _q_parse(q):
    y, qq = q.split("Q")
    return int(y), int(qq)


def _q_key(q):
    y, qq = _q_parse(q)
    return y * 4 + qq


def _q_end_date(q):
    y, qq = _q_parse(q)
    m, d = _Q_END[qq]
    return f"{y}-{m:02d}-{d:02d}"


def score_transcripts(conn, run_id: str) -> int:
    """Score every stored transcript (TF-IDF corpus weighting) → company_scores."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT company, country_iso, sector, quarter, transcript_text, "
            "source_name FROM cldv_transcripts WHERE transcript_text IS NOT NULL"
        )
        rows = cur.fetchall()
    if not rows:
        print("[SI1] no transcripts to score")
        return 0

    docs = [r[4] for r in rows]
    scored = score_corpus(docs)            # TF-IDF proxy across the whole corpus

    with conn.cursor() as cur:
        for (company, iso, sector, quarter, _txt, sname), s in zip(rows, scored):
            cur.execute(
                """
                INSERT INTO cldv_si1_company_scores
                    (company, country_iso, sector, quarter, word_count, ai_density,
                     proxy_score, strict_score, employees, source_name, run_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company, quarter) DO UPDATE SET
                    proxy_score=EXCLUDED.proxy_score, strict_score=EXCLUDED.strict_score,
                    ai_density=EXCLUDED.ai_density, word_count=EXCLUDED.word_count,
                    employees=EXCLUDED.employees, source_name=EXCLUDED.source_name,
                    run_id=EXCLUDED.run_id, scored_at=now()
                """,
                (company, iso, sector, quarter, s.get("word_count"),
                 s.get("ai_density"), s.get("proxy_score"), s.get("strict_score"),
                 employees_for(company), sname, run_id),
            )
    conn.commit()
    print(f"[SI1] scored {len(rows)} transcripts")
    return len(rows)


def aggregate_rows(rows):
    """Pure: rows of (iso, quarter, proxy, strict, employees) →
    {iso: {quarter: {'proxy':w, 'strict':w, 'n':k}}} employment-weighted."""
    acc = {}
    for iso, q, proxy, strict, emp in rows:
        if proxy is None:
            continue
        emp = float(emp or 0) or 1.0
        d = acc.setdefault(iso, {}).setdefault(q, {"pw": 0.0, "sw": 0.0, "w": 0.0, "n": 0})
        d["pw"] += float(proxy) * emp
        d["sw"] += float(strict or 0) * emp
        d["w"]  += emp
        d["n"]  += 1
    return {iso: {q: {"proxy": d["pw"] / d["w"], "strict": d["sw"] / d["w"], "n": d["n"]}
                  for q, d in qs.items()}
            for iso, qs in acc.items()}


def velocity_for_country(qmap):
    """Pure: {quarter: {'proxy','strict'}} → latest level + QoQ velocity."""
    quarters = sorted(qmap, key=_q_key)
    if not quarters:
        return None
    latest = quarters[-1]
    res = {"latest": latest, "prev": None,
           "level_proxy": qmap[latest]["proxy"],
           "level_strict": qmap[latest]["strict"], "velocity": None}
    if len(quarters) >= 2:
        prev = quarters[-2]
        res["prev"] = prev
        res["velocity"] = qmap[latest]["proxy"] - qmap[prev]["proxy"]
    return res


def _country_quarter_aggregates(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT country_iso, quarter, proxy_score, strict_score, employees "
            "FROM cldv_si1_company_scores WHERE proxy_score IS NOT NULL"
        )
        rows = cur.fetchall()
    return aggregate_rows(rows)


def aggregate_and_write_metrics(conn, run_id: str):
    """Employment-weighted country aggregate → QoQ velocity → SI1 raw metrics."""
    agg = _country_quarter_aggregates(conn)
    written = gaps = 0

    def _store(iso, key, label, value, unit, q):
        nonlocal written
        dp = make_metric_result(
            iso, "SI1", key, round(value, 4), unit, _q_end_date(q), "quarterly",
            "CLDV NLP (earnings transcripts)", None, "nlp_derived", 0.70,
            metric_label=label, raw_value=f"latest_quarter={q}")
        store_metric_datapoint(conn, dp, run_id)
        written += 1

    for iso in COUNTRIES:
        v = velocity_for_country(agg.get(iso, {}))
        if v is None:
            open_gap(conn, iso, "SI1", "corporate_displacement_velocity",
                     "no scored transcripts for this country", ["NLP"],
                     severity="high",
                     metric_label="Corporate displacement velocity")
            gaps += 1
            continue
        latest = v["latest"]
        _store(iso, "corporate_displacement_level",
               "Corporate displacement level (latest quarter, proxy)",
               v["level_proxy"], "score_-1_1", latest)
        _store(iso, "corporate_displacement_strict",
               "Strict AI-attributed displacement level (latest quarter)",
               v["level_strict"], "score_-1_1", latest)
        if v["velocity"] is not None:
            _store(iso, "corporate_displacement_velocity",
                   "Corporate displacement velocity (QoQ Δ, employment-weighted)",
                   v["velocity"], "qoq_delta", latest)
        else:
            open_gap(conn, iso, "SI1", "corporate_displacement_velocity",
                     f"only 1 quarter ({latest}) — need ≥2 for QoQ velocity",
                     ["NLP"], severity="high",
                     metric_label="Corporate displacement velocity")
            gaps += 1

    conn.commit()
    print(f"[SI1] aggregation: {written} metrics written, {gaps} gaps")
    return written, gaps


def run_si1_scoring(conn, run_id: str) -> dict:
    n = score_transcripts(conn, run_id)
    written, gaps = aggregate_and_write_metrics(conn, run_id)
    return {"transcripts_scored": n, "metrics_written": written, "gaps": gaps}
