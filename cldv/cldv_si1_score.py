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
from cldv_si1_headcount import latest_employees
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
            "source_name, source_url FROM cldv_transcripts "
            "WHERE transcript_text IS NOT NULL"
        )
        rows = cur.fetchall()
    if not rows:
        print("[SI1] no transcripts to score")
        return 0

    docs = [r[4] for r in rows]
    scored = score_corpus(docs)            # TF-IDF proxy across the whole corpus
    emp_map = latest_employees(conn)       # dated, sourced headcounts (fallback: static)

    with conn.cursor() as cur:
        for (company, iso, sector, quarter, _txt, sname, surl), s in zip(rows, scored):
            cur.execute(
                """
                INSERT INTO cldv_si1_company_scores
                    (company, country_iso, sector, quarter, word_count, ai_density,
                     proxy_score, strict_score, employees, source_name, source_url, run_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company, quarter) DO UPDATE SET
                    proxy_score=EXCLUDED.proxy_score, strict_score=EXCLUDED.strict_score,
                    ai_density=EXCLUDED.ai_density, word_count=EXCLUDED.word_count,
                    employees=EXCLUDED.employees, source_name=EXCLUDED.source_name,
                    source_url=EXCLUDED.source_url, run_id=EXCLUDED.run_id, scored_at=now()
                """,
                (company, iso, sector, quarter, s.get("word_count"),
                 s.get("ai_density"), s.get("proxy_score"), s.get("strict_score"),
                 emp_map.get(company) or employees_for(company), sname, surl, run_id),
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


def _lineage(conn):
    """{country: {quarter: [(company, transcript_url), …]}} — provenance for
    each SI1 aggregate metric."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT country_iso, quarter, company, source_url "
            "FROM cldv_si1_company_scores WHERE proxy_score IS NOT NULL"
        )
        rows = cur.fetchall()
    out = {}
    for iso, q, company, url in rows:
        out.setdefault(iso, {}).setdefault(q, []).append((company, url))
    return out


def aggregate_and_write_metrics(conn, run_id: str):
    """Employment-weighted country aggregate → QoQ velocity → SI1 raw metrics."""
    agg = _country_quarter_aggregates(conn)
    lineage = _lineage(conn)        # {country: {quarter: [(company, url), …]}}
    written = gaps = 0

    def _store(iso, key, label, value, unit, q, quarters_used):
        nonlocal written
        contribs = [cu for qu in quarters_used for cu in lineage.get(iso, {}).get(qu, [])]
        src_url = next((u for _c, u in contribs if u), None)
        raw = (f"quarters={quarters_used}; employment-weighted over "
               f"{len(contribs)} transcripts: "
               + "; ".join(f"{c}({u})" for c, u in contribs))
        dp = make_metric_result(
            iso, "SI1", key, round(value, 4), unit, _q_end_date(q), "quarterly",
            f"CLDV NLP (employment-weighted, {len(contribs)} transcripts)",
            src_url, "nlp_derived", 0.70, metric_label=label, raw_value=raw)
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
               v["level_proxy"], "score_-1_1", latest, [latest])
        _store(iso, "corporate_displacement_strict",
               "Strict AI-attributed displacement level (latest quarter)",
               v["level_strict"], "score_-1_1", latest, [latest])
        if v["velocity"] is not None:
            _store(iso, "corporate_displacement_velocity",
                   "Corporate displacement velocity (QoQ Δ, employment-weighted)",
                   v["velocity"], "qoq_delta", latest, [v["prev"], latest])
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
