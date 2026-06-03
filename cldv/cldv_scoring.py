"""CLDV scoring — min-max normalize each scored metric 0–100 across the 6
countries (invert where "lower raw = more displacement"), weight per the DB
methodology, aggregate to sub-indices and the final CLDV.

Mirrors the WS2 scoring contract: weights live in cldv_score_methodology /
cldv_subindex_weights, selection is confidence-first, missing data contributes 0
(weight is NOT redistributed). During incremental build, sub-indices with no
scored metrics yet (SI1/SI2) are reported as NULL and excluded from the weighted
sum — CLDV is therefore PROVISIONAL until all three sub-indices are populated.

Public entry point: run_scoring(conn, run_id) -> dict of final scores.
"""
from cldv_db import COUNTRIES


def _minmax(values: dict, invert: bool = False) -> dict:
    """Min-max scale {iso2: raw} → {iso2: 0..100}. All-equal → 50. invert: low→high."""
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return {}
    lo, hi = min(present.values()), max(present.values())
    out = {}
    for k, v in present.items():
        s = 50.0 if hi == lo else (v - lo) / (hi - lo) * 100.0
        out[k] = round(100.0 - s if invert else s, 4)
    return out


def _load_methodology(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT sub_index, metric_key, weight, invert "
                    "FROM cldv_score_methodology WHERE scored = TRUE")
        metrics = cur.fetchall()
        cur.execute("SELECT sub_index, weight FROM cldv_subindex_weights")
        sub_weights = dict(cur.fetchall())
    return metrics, sub_weights


def _latest_value_per_country(conn, sub_index, metric_key) -> dict:
    """Confidence-first, then recency: one value per country."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (country_iso) country_iso, metric_value
            FROM cldv_raw_metrics
            WHERE sub_index = %s AND metric_key = %s AND metric_value IS NOT NULL
            ORDER BY country_iso, confidence_score DESC NULLS LAST, data_date DESC
            """,
            (sub_index, metric_key),
        )
        return {iso2: float(v) for iso2, v in cur.fetchall()}


def run_scoring(conn, run_id: str) -> dict:
    print("[SCORING] loading methodology…")
    metrics, sub_weights = _load_methodology(conn)

    # accumulate weighted normalized scores per (country, sub_index)
    sub_acc = {iso2: {} for iso2 in COUNTRIES}

    with conn.cursor() as cur:
        cur.execute("DELETE FROM cldv_score_metric_normalized WHERE run_id=%s", (run_id,))
        cur.execute("DELETE FROM cldv_score_subindex WHERE run_id=%s", (run_id,))
        cur.execute("DELETE FROM cldv_score_final WHERE run_id=%s", (run_id,))
    conn.commit()

    for sub_index, metric_key, weight, invert in metrics:
        raw = _latest_value_per_country(conn, sub_index, metric_key)
        norm = _minmax(raw, invert=invert)
        if not norm:
            print(f"  [SCORING] {sub_index}/{metric_key}: no data — skipped")
            continue
        with conn.cursor() as cur:
            for iso2, n in norm.items():
                weighted = round(n * float(weight), 4)
                cur.execute(
                    """
                    INSERT INTO cldv_score_metric_normalized
                        (run_id, country_iso, sub_index, metric_key, raw_value,
                         normalized, invert, weight, weighted_score)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (run_id, iso2, sub_index, metric_key, raw.get(iso2),
                     n, invert, float(weight), weighted),
                )
                sub_acc[iso2].setdefault(sub_index, 0.0)
                sub_acc[iso2][sub_index] += weighted
        conn.commit()
        print(f"  [SCORING] {sub_index}/{metric_key}: normalized {len(norm)} countries "
              f"(invert={invert})")

    # sub-index scores
    with conn.cursor() as cur:
        for iso2 in COUNTRIES:
            for sub_index, sub_score in sub_acc[iso2].items():
                w = float(sub_weights.get(sub_index, 0))
                cur.execute(
                    """
                    INSERT INTO cldv_score_subindex
                        (run_id, country_iso, sub_index, subindex_score, weight, weighted_score)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (run_id, iso2, sub_index, round(sub_score, 4), w,
                     round(sub_score * w, 4)),
                )
    conn.commit()

    # final CLDV = Σ(subindex_score × subindex_weight) over PRESENT sub-indices
    finals = []
    for iso2, meta in COUNTRIES.items():
        subs = sub_acc[iso2]
        si1 = subs.get("SI1")
        si2 = subs.get("SI2")
        si3 = subs.get("SI3")
        cldv = sum((subs[s] * float(sub_weights.get(s, 0))) for s in subs)
        finals.append([iso2, meta["name"], si1, si2, si3, round(cldv, 4)])

    finals.sort(key=lambda r: r[5], reverse=True)
    with conn.cursor() as cur:
        for rank, row in enumerate(finals, start=1):
            iso2, name, si1, si2, si3, cldv = row
            cur.execute(
                """
                INSERT INTO cldv_score_final
                    (run_id, country_iso, country_name, si1_corporate, si2_labor,
                     si3_services, cldv_score, rank)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (run_id, iso2, name, si1, si2, si3, cldv, rank),
            )
    conn.commit()

    present = sorted({s for acc in sub_acc.values() for s in acc})
    missing = [s for s in ("SI1", "SI2", "SI3") if s not in present]
    if missing:
        print(f"[SCORING] ⚠ PROVISIONAL CLDV — sub-indices not yet populated: "
              f"{', '.join(missing)}. Final score reflects only {present}.")
    print("[SCORING] done.")
    return {r[0]: r[5] for r in finals}
