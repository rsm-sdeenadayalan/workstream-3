"""SI3 — Services Trade Flow Signal collectors.

All four metrics come from the World Bank WDI API (free, no key), validated for
all six countries. The single SCORED metric (per spec) is the currency-adjusted
rate-of-change of services exports per capita; the other three are stored as
tracked context. World Bank series are current-US$ so they are inherently
currency-comparable across countries ("currency-adjusted").

Public entry point: run_si3(conn, run_id) -> (succeeded, failed, gaps)
"""
import os
import time
import requests

from cldv_db import (COUNTRIES, CONFIDENCE, make_metric_result,
                     store_metric_datapoint, log_attempt, open_gap)

WB_BASE = "https://api.worldbank.org/v2"
ISO3S   = ";".join(c["iso3"] for c in COUNTRIES.values())
ISO3_TO_ISO2 = {c["iso3"]: iso2 for iso2, c in COUNTRIES.items()}
MRV = max(3, int(os.environ.get("CLDV_WB_MRV", "8")))

# World Bank indicator codes
IND = {
    "svc_exports":  "BX.GSR.NFSV.CD",   # Service exports (BoP, current US$)
    "svc_imports":  "BM.GSR.NFSV.CD",   # Service imports (BoP, current US$)
    "gdp":          "NY.GDP.MKTP.CD",   # GDP (current US$)
    "population":   "SP.POP.TOTL",      # Total population
    "ict_pct_svc":  "BX.GSR.CMCP.ZS",   # ICT service exports (% of service exports)
}

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Gramercy-CLDV/0.1 (research)"})


def worldbank_get(indicator: str, mrv: int = MRV) -> dict:
    """Fetch one indicator for all 6 countries. Returns {iso3: {year:int -> value:float}}
    with null years dropped."""
    url = f"{WB_BASE}/country/{ISO3S}/indicator/{indicator}"
    params = {"format": "json", "mrv": mrv, "per_page": 500}
    for attempt in range(4):
        try:
            r = _SESSION.get(url, params=params, timeout=30)
            if r.status_code == 200:
                payload = r.json()
                break
            time.sleep(2 ** attempt)
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"World Bank fetch failed: {indicator}")

    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and payload[1] else []
    out: dict = {}
    for row in rows:
        iso3 = row.get("countryiso3code")
        val  = row.get("value")
        try:
            year = int(row.get("date"))
        except (TypeError, ValueError):
            continue
        if iso3 and val is not None:
            out.setdefault(iso3, {})[year] = float(val)
    return out


def _wb_url(indicator: str) -> str:
    return f"https://data.worldbank.org/indicator/{indicator}"


def _latest_two(series: dict):
    """Return (year_latest, val_latest, year_prev, val_prev) from a {year:value}
    dict, or (None,...) if fewer than the needed points exist."""
    if not series:
        return (None, None, None, None)
    years = sorted(series.keys(), reverse=True)
    y0 = years[0]
    y1 = years[1] if len(years) > 1 else None
    return (y0, series[y0], y1, series[y1] if y1 is not None else None)


def run_si3(conn, run_id: str):
    """Collect all SI3 services-trade metrics for the 6 countries."""
    print("[SI3] Fetching World Bank WDI indicators…")
    data = {}
    for key, code in IND.items():
        try:
            data[key] = worldbank_get(code)
            n = sum(len(v) for v in data[key].values())
            print(f"  [WB] {code:18s} ({key}): {n} country-year points")
        except Exception as e:
            print(f"  [WB] {code} FAILED: {e}")
            data[key] = {}

    succeeded = failed = gaps = 0

    def _api_url(iso3, indicator, year):
        # working URL that returns the exact value as JSON
        return (f"{WB_BASE}/country/{iso3}/indicator/{indicator}"
                f"?format=json&date={year}")

    def _store(iso2, metric_key, label, value, unit, data_year, indicators, components):
        """indicators: WB codes this metric derives from (primary first).
        components: human-readable computation w/ the actual numbers used."""
        nonlocal succeeded
        iso3 = COUNTRIES[iso2]["iso3"]
        primary = indicators[0]
        url = _api_url(iso3, primary, data_year)
        raw = f"{components} | World Bank indicators: {', '.join(indicators)}"
        dp = make_metric_result(
            iso2, "SI3", metric_key, value, unit,
            f"{data_year}-12-31", "annual",
            f"World Bank WDI ({primary})", url,
            "worldbank_api", CONFIDENCE["worldbank_api"],
            metric_label=label, raw_value=raw,
        )
        store_metric_datapoint(conn, dp, run_id)
        log_attempt(conn, run_id, iso2, metric_key, f"World Bank WDI ({primary})",
                    1, "success", source_url=url)
        succeeded += 1

    def _gap(iso2, metric_key, label, reason, severity="medium"):
        nonlocal failed, gaps
        log_attempt(conn, run_id, iso2, metric_key, "World Bank WDI", 1,
                    "failed", error_type="NoData", error_message=reason)
        open_gap(conn, iso2, "SI3", metric_key, reason, ["World Bank WDI"],
                 severity=severity, metric_label=label)
        failed += 1
        gaps += 1

    for iso2, meta in COUNTRIES.items():
        iso3 = meta["iso3"]
        svc  = data["svc_exports"].get(iso3, {})
        imp  = data["svc_imports"].get(iso3, {})
        gdp  = data["gdp"].get(iso3, {})
        pop  = data["population"].get(iso3, {})
        ict  = data["ict_pct_svc"].get(iso3, {})

        # 1. Services exports % of GDP (latest common year)
        common = sorted(set(svc) & set(gdp), reverse=True)
        if common:
            y = common[0]
            _store(iso2, "services_exports_pct_gdp",
                   "Services exports (% of GDP)",
                   round(svc[y] / gdp[y] * 100, 4), "pct_gdp", y,
                   ["BX.GSR.NFSV.CD", "NY.GDP.MKTP.CD"],
                   f"svc_exports={svc[y]:.4e} / GDP={gdp[y]:.4e} ({y})")
        else:
            _gap(iso2, "services_exports_pct_gdp", "Services exports (% of GDP)",
                 "No overlapping services-exports / GDP year")

        # 2. Services exports per capita (level) + 3. its YoY % change (SCORED)
        pc_years = sorted(set(svc) & set(pop), reverse=True)
        percap = {y: svc[y] / pop[y] for y in pc_years}
        y0, v0, y1, v1 = _latest_two(percap)
        if y0 is not None:
            _store(iso2, "services_exports_per_capita",
                   "Services exports per capita (USD)", round(v0, 2),
                   "usd_per_capita", y0,
                   ["BX.GSR.NFSV.CD", "SP.POP.TOTL"],
                   f"svc_exports={svc[y0]:.4e} / pop={pop[y0]:.0f} ({y0})")
        else:
            _gap(iso2, "services_exports_per_capita",
                 "Services exports per capita (USD)", "No services/population year")

        if y0 is not None and y1 is not None and v1:
            yoy = (v0 - v1) / v1 * 100
            _store(iso2, "services_exports_per_capita_yoy",
                   "Services exports per capita, YoY % change",
                   round(yoy, 4), "pct_yoy", y0,
                   ["BX.GSR.NFSV.CD", "SP.POP.TOTL"],
                   f"per_capita {y1}->{y0}: {v1:.1f}->{v0:.1f} USD")
        else:
            _gap(iso2, "services_exports_per_capita_yoy",
                 "Services exports per capita, YoY % change",
                 "Need two years of services-exports-per-capita", severity="high")

        # 4. IT/BPO services export growth (YoY %) — ICT exports value = svc × ICT%
        ict_val = {y: svc[y] * ict[y] / 100 for y in (set(svc) & set(ict))}
        iy0, iv0, iy1, iv1 = _latest_two(ict_val)
        if iy0 is not None and iy1 is not None and iv1:
            _store(iso2, "it_bpo_export_growth_yoy",
                   "IT/BPO services export growth (YoY %)",
                   round((iv0 - iv1) / iv1 * 100, 4), "pct_yoy", iy0,
                   ["BX.GSR.CMCP.ZS", "BX.GSR.NFSV.CD"],
                   f"ICT%×svc_exports {iy1}->{iy0}: {iv1:.4e}->{iv0:.4e} USD")
        else:
            _gap(iso2, "it_bpo_export_growth_yoy",
                 "IT/BPO services export growth (YoY %)",
                 "Need two years of ICT-services export value", severity="low")

        # 5. Current-account services balance (exports − imports), latest common year
        bal_years = sorted(set(svc) & set(imp), reverse=True)
        if bal_years:
            y = bal_years[0]
            _store(iso2, "current_account_services_balance",
                   "Current-account services balance (USD)",
                   round(svc[y] - imp[y], 2), "usd", y,
                   ["BX.GSR.NFSV.CD", "BM.GSR.NFSV.CD"],
                   f"exports={svc[y]:.4e} - imports={imp[y]:.4e} ({y})")
        else:
            _gap(iso2, "current_account_services_balance",
                 "Current-account services balance (USD)",
                 "No overlapping services exports/imports year")

    print(f"[SI3] done — {succeeded} stored, {failed} gaps")
    return succeeded, failed, gaps
