"""Latest reported employee headcount per company — dated + sourced.

Companies report headcount every quarter, so the latest figure is always
available with a date and a source URL (unlike a static approximation). This
fetches it via web search, parses the most-recent (count, as-of-date) pair, and
stores it in cldv_si1_headcount for the employment-weighted SI1 aggregation.

Public entry point: run_headcount(conn, run_id) -> (ok, miss)
"""
import os
import re
from collections import Counter
from datetime import date

import requests

from cldv_db import get_conn
from cldv_si1_companies import active_companies, EMPLOYEES

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

_KEY = os.environ.get("TAVILY_API_KEY", "")
_UA = {"User-Agent": "Gramercy Capstone research capstoneagentic@gmail.com"}

# ── SEC EDGAR (primary source — same filings Capital IQ/Revelio parse) ────────
_HC_PATS = [
    re.compile(r"(?:had|have|employed|approximately|totaled|of|were)\s+"
               r"(?:approximately\s+)?([\d][\d,]{3,})\s+"
               r"(?:full[- ]time\s+|total\s+|regular\s+)?"
               r"(?:employees|people|persons|staff|professionals)", re.I),
    re.compile(r"([\d][\d,]{3,})\s+(?:full[- ]time\s+)?(?:employees|people)", re.I),
]
_cik_cache = None


def _cik_map():
    global _cik_cache
    if _cik_cache is None:
        try:
            tj = requests.get("https://www.sec.gov/files/company_tickers.json",
                              headers=_UA, timeout=30).json()
            _cik_cache = {row["ticker"].upper(): f'{row["cik_str"]:010d}'
                          for row in tj.values()}
        except Exception:
            _cik_cache = {}
    return _cik_cache


def _sec_latest_filing(cik):
    """(doc_url, form, report_date) for the latest 10-K/20-F, or None."""
    try:
        sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                           headers=_UA, timeout=30).json()
    except Exception:
        return None
    r = sub["filings"]["recent"]
    for form, acc, doc, rdt in zip(r["form"], r["accessionNumber"],
                                   r["primaryDocument"], r["reportDate"]):
        if form in ("10-K", "20-F"):
            a = acc.replace("-", "")
            return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{doc}",
                    form, rdt)
    return None


def _extract_headcount(text):
    """Most-frequent plausible headcount (≥5000) near an 'employees' phrase."""
    vals = []
    for p in _HC_PATS:
        for m in p.finditer(text):
            n = int(m.group(1).replace(",", ""))
            if 5000 <= n <= 3_000_000:
                vals.append(n)
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def fetch_headcount_sec(ticker):
    """Primary path: (employees, as_of, url, 'SEC <form>') from EDGAR, or None."""
    cik = _cik_map().get((ticker or "").upper())
    if not cik:
        return None
    info = _sec_latest_filing(cik)
    if not info:
        return None
    url, form, rdt = info
    try:
        html = requests.get(url, headers=_UA, timeout=60).text
    except Exception:
        return None
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    emp = _extract_headcount(text)
    if emp is None:
        return None
    return emp, rdt, url, f"SEC {form}"
_NUM = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_DATE = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\w*\s+(?:\d{1,2},?\s*)?(\d{4})", re.I)


def _parse_date(m):
    return date(int(m.group(2)), _MONTHS[m.group(1).lower()], 1)


def parse_headcount(answer: str):
    """Return {'employees': int, 'as_of': 'YYYY-MM-DD'|None} from a text answer,
    picking the count paired with the most-recent date."""
    if not answer:
        return None
    nums = [(int(m.group().replace(",", "")), m.start()) for m in _NUM.finditer(answer)]
    nums = [(n, p) for n, p in nums if 500 <= n <= 5_000_000]
    if not nums:
        return None
    dates = [(_parse_date(m), m.start()) for m in _DATE.finditer(answer)]
    if dates:
        best = None
        for n, p in nums:
            d, _ = min(dates, key=lambda dp: abs(dp[1] - p))
            if best is None or d > best[0]:
                best = (d, n)
        return {"employees": best[1], "as_of": best[0].isoformat()}
    return {"employees": nums[0][0], "as_of": None}


def _fetch_headcount_tavily(tv, company_name):
    """Fallback path: (employees, as_of, url, 'Web aggregator') or None."""
    if not tv:
        return None
    try:
        r = tv.search(query=f"{company_name} total number of employees latest 2025 2026",
                      max_results=4, include_answer=True)
    except Exception:
        return None
    parsed = parse_headcount(r.get("answer") or "")
    if not parsed:
        return None
    src = r["results"][0]["url"] if r.get("results") else None
    return parsed["employees"], parsed["as_of"], src, "Web aggregator"


def fetch_headcount(tv, company: dict):
    """SEC filing first (primary), then web-aggregator fallback.
    Returns (employees, as_of, source_url, source_name) or None."""
    sec = fetch_headcount_sec(company.get("us_ticker"))
    if sec:
        return sec
    return _fetch_headcount_tavily(tv, company["company"])


def run_headcount(conn, run_id: str):
    tv = TavilyClient(api_key=_KEY) if (_KEY and TavilyClient) else None
    sec = web = static = 0
    for c in active_companies():
        name = c["company"]
        res = fetch_headcount(tv, c)
        if res:
            emp, as_of, url, sname = res
            if sname.startswith("SEC"):
                sec += 1
            else:
                web += 1
        else:                                    # curated static fallback
            emp, as_of, url, sname = EMPLOYEES.get(name), None, None, "static estimate"
            static += 1
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cldv_si1_headcount
                    (company, country_iso, employees, as_of_date, source_name,
                     source_url, run_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company) DO UPDATE SET
                    employees=EXCLUDED.employees, as_of_date=EXCLUDED.as_of_date,
                    source_name=EXCLUDED.source_name, source_url=EXCLUDED.source_url,
                    run_id=EXCLUDED.run_id, collected_at=now()
                """,
                (name, c["country_iso"], emp, as_of, sname, url, run_id),
            )
    conn.commit()
    print(f"[SI1] headcount: {sec} from SEC filings, {web} from web aggregators, "
          f"{static} static fallback")
    return sec + web, static


def latest_employees(conn):
    """{company: employees} from the dated headcount table (for aggregation)."""
    with conn.cursor() as cur:
        cur.execute("SELECT company, employees FROM cldv_si1_headcount "
                    "WHERE employees IS NOT NULL")
        return dict(cur.fetchall())


if __name__ == "__main__":
    c = get_conn()
    run_headcount(c, "manual")
