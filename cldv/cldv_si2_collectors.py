"""SI2 — Labor Market Signal.

Free backbone: ILOSTAT employment-by-occupation (ISCO-08), no key required. The
spec's job-posting "crossover ratio" has no free historical source, so we use an
employment-stock proxy: clerical/cognitive labour (ISCO 4) relative to
AI-adjacent professionals (ISCO 2, which includes ICT professionals). A FALLING
ratio = cognitive labour shrinking relative to AI-adjacent roles = displacement.

Scored metric (per spec — "the crossover ratio and its rate of change"):
crossover_ratio_yoy, inverted (falling ratio → higher displacement). Component
YoY series are stored as tracked context. Every value carries its exact ILOSTAT
API URL + the computation.

NOTE (documented limitation): ISCO 1-digit groups are coarse — some at-risk
cognitive roles (analysts, accountants) sit in ISCO 2 alongside AI-adjacent
professionals. This is an employment-stock proxy, not job postings.

Public entry point: run_si2(conn, run_id) -> (succeeded, failed, gaps)
"""
import csv
import io

import requests

from cldv_db import (COUNTRIES, CONFIDENCE, make_metric_result,
                     store_metric_datapoint, log_attempt, open_gap)

ILO_BASE = "https://rplumber.ilo.org/data/indicator/"
_UA = {"User-Agent": "Gramercy CLDV research capstoneagentic@gmail.com"}

COGNITIVE_ISCO = "OCU_ISCO08_4"   # clerical support workers (automatable cognitive)
AI_ADJ_ISCO    = "OCU_ISCO08_2"   # professionals incl. ICT (AI-adjacent)


def _ilo_url(iso3, timefrom=2017):
    return (f"{ILO_BASE}?id=EMP_TEMP_SEX_OCU_NB_A&ref_area={iso3}"
            f"&timefrom={timefrom}&format=.csv")


def ilostat_occupation(iso3):
    """Return ({classif1: {year: value_thousands}}, url) for SEX_T."""
    url = _ilo_url(iso3)
    r = requests.get(url, headers=_UA, timeout=45)
    r.raise_for_status()
    out = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        if row.get("sex") != "SEX_T":
            continue
        try:
            y, v = int(row["time"]), float(row["obs_value"])
        except (TypeError, ValueError):
            continue
        out.setdefault(row["classif1"], {})[y] = v
    return out, url


def _latest_two(series):
    ys = sorted(series, reverse=True)
    if not ys:
        return (None, None, None, None)
    y0 = ys[0]
    y1 = ys[1] if len(ys) > 1 else None
    return (y0, series[y0], y1, series[y1] if y1 is not None else None)


def run_si2(conn, run_id: str):
    print("[SI2] Fetching ILOSTAT employment-by-occupation (ISCO-08)…")
    succeeded = failed = gaps = 0

    def _store(iso2, key, label, value, unit, year, url, components):
        nonlocal succeeded
        dp = make_metric_result(
            iso2, "SI2", key, round(value, 4), unit, f"{year}-12-31", "annual",
            "ILOSTAT (EMP_TEMP_SEX_OCU_NB, ISCO-08)", url, "ilostat_api",
            CONFIDENCE.get("worldbank_api", 0.9), metric_label=label,
            raw_value=f"{components} | ILOSTAT EMP_TEMP_SEX_OCU_NB")
        store_metric_datapoint(conn, dp, run_id)
        log_attempt(conn, run_id, iso2, key, "ILOSTAT", 1, "success", source_url=url)
        succeeded += 1

    def _gap(iso2, key, label, reason, sev="medium"):
        nonlocal failed, gaps
        log_attempt(conn, run_id, iso2, key, "ILOSTAT", 1, "failed",
                    error_message=reason)
        open_gap(conn, iso2, "SI2", key, reason, ["ILOSTAT"], severity=sev,
                 metric_label=label)
        failed += 1
        gaps += 1

    for iso2, meta in COUNTRIES.items():
        try:
            data, url = ilostat_occupation(meta["iso3"])
        except Exception as e:
            for k, lbl in (("crossover_ratio_yoy", "Crossover ratio YoY"),
                           ("crossover_ratio", "Crossover ratio"),
                           ("cognitive_labor_yoy", "Cognitive labour YoY"),
                           ("ai_adjacent_yoy", "AI-adjacent YoY")):
                _gap(iso2, k, lbl, f"ILOSTAT fetch failed: {e}",
                     sev="high" if k == "crossover_ratio_yoy" else "medium")
            continue

        cog = data.get(COGNITIVE_ISCO, {})
        ai  = data.get(AI_ADJ_ISCO, {})
        years = sorted(set(cog) & set(ai))
        ratio = {y: cog[y] / ai[y] for y in years if ai.get(y)}

        ry0, rv0, ry1, rv1 = _latest_two(ratio)
        if ry0 is not None:
            _store(iso2, "crossover_ratio",
                   "Cognitive(ISCO4)/AI-adjacent(ISCO2) employment ratio",
                   rv0, "ratio", ry0, url,
                   f"ISCO4={cog[ry0]:.1f}k / ISCO2={ai[ry0]:.1f}k ({ry0})")
        else:
            _gap(iso2, "crossover_ratio", "Crossover ratio",
                 "No overlapping ISCO-4 / ISCO-2 year")

        if ry0 is not None and ry1 is not None and rv1:
            _store(iso2, "crossover_ratio_yoy",
                   "Crossover ratio, YoY % change (falling = displacement)",
                   (rv0 - rv1) / rv1 * 100, "pct_yoy", ry0, url,
                   f"ratio {ry1}->{ry0}: {rv1:.4f}->{rv0:.4f}")
        else:
            _gap(iso2, "crossover_ratio_yoy", "Crossover ratio YoY",
                 "Need two years of ISCO-4/ISCO-2 ratio", sev="high")

        cy0, cv0, cy1, cv1 = _latest_two(cog)
        if cy0 is not None and cy1 is not None and cv1:
            _store(iso2, "cognitive_labor_yoy",
                   "Clerical/cognitive (ISCO-4) employment, YoY %",
                   (cv0 - cv1) / cv1 * 100, "pct_yoy", cy0, url,
                   f"ISCO4 {cy1}->{cy0}: {cv1:.1f}k->{cv0:.1f}k")

        ay0, av0, ay1, av1 = _latest_two(ai)
        if ay0 is not None and ay1 is not None and av1:
            _store(iso2, "ai_adjacent_yoy",
                   "AI-adjacent professionals (ISCO-2) employment, YoY %",
                   (av0 - av1) / av1 * 100, "pct_yoy", ay0, url,
                   f"ISCO2 {ay1}->{ay0}: {av1:.1f}k->{av0:.1f}k")

    print(f"[SI2] done — {succeeded} stored, {gaps} gaps")
    return succeeded, failed, gaps
