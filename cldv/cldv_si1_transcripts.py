"""SI1 transcript collector — primary source is the company's own investor-
relations PDF (authoritative + freshest), located via domain-restricted web
search; Motley Fool / EDGAR-style transcript pages are the fallback. Always
works newest-quarter-first so the most recent data drives the score.

Cells are independent and I/O-bound (search + download + parse), so they run on
a thread pool with per-thread DB connections (the WS1 pattern).

Public entry point: run_si1_transcripts(conn, run_id, n_quarters) -> (ok, fail)
"""
import io
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

from cldv_db import (CONFIDENCE, get_conn, log_attempt, open_gap)
from cldv_si1_companies import active_companies, us_listed

try:
    import pdfplumber
except ImportError:
    pdfplumber = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
_TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
_MAX_WORKERS = max(1, int(os.environ.get("CLDV_MAX_WORKERS", "6")))


# ── Quarter helpers (newest-first) ───────────────────────────────────────────
def _latest_reported_quarter():
    """The most recent calendar quarter likely already reported (~6 weeks lag)."""
    d = datetime.utcnow() - timedelta(days=75)
    return d.year, (d.month - 1) // 3 + 1


def recent_quarters(n: int):
    y, q = _latest_reported_quarter()
    out = []
    for _ in range(n):
        out.append((y, q))
        q -= 1
        if q == 0:
            q = 4; y -= 1
    return out                       # newest first


def qlabel(y, q):
    return f"{y}Q{q}"


# ── Search + fetch ───────────────────────────────────────────────────────────
def _tavily():
    if not (_TAVILY_KEY and TavilyClient):
        return None
    return TavilyClient(api_key=_TAVILY_KEY)


def _search(query, include_domains=None, n=6):
    tv = _tavily()
    if not tv:
        return []
    try:
        kw = {"query": query, "max_results": n}
        if include_domains:
            kw["include_domains"] = include_domains
        return [r["url"] for r in tv.search(**kw).get("results", [])]
    except Exception:
        return []


def _fetch_pdf_text(url):
    if not pdfplumber:
        return None
    r = requests.get(url, headers=_UA, timeout=60)
    if r.status_code != 200 or "pdf" not in r.headers.get("content-type", "").lower():
        return None
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _fetch_html_text(url):
    if not BeautifulSoup:
        return None
    r = requests.get(url, headers=_UA, timeout=45)
    if r.status_code != 200:
        return None
    body = BeautifulSoup(r.text, "lxml")
    node = body.find("div", class_="article-body") or body.find("article") or body.body
    return node.get_text(" ", strip=True) if node else None


_GENERIC_NAME_WORDS = {"group", "holdings", "limited", "ltd", "inc",
                       "incorporated", "corporation", "corp", "co", "plc",
                       "sa", "nv", "the", "platforms", "company", "services",
                       "service", "and"}


def _identity_tokens(company: dict) -> set:
    """Distinctive name/ticker tokens used to confirm a doc is the RIGHT firm."""
    name = re.sub(r"[^\w\s&]", " ", company["company"].lower())
    toks = {w for w in name.split() if w not in _GENERIC_NAME_WORDS and len(w) >= 3}
    if company.get("us_ticker"):
        toks.add(company["us_ticker"].lower())
    return toks or {company["company"].split()[0].lower()}


_MIN_TRANSCRIPT_WORDS = 2500   # real earnings-call transcripts run 3k–25k words


def _looks_like_transcript(text) -> bool:
    if not text or len(text.split()) < _MIN_TRANSCRIPT_WORDS:
        return False
    low = text.lower()
    return ("transcript" in low or "earnings call" in low
            or "prepared remarks" in low or "question-and-answer" in low
            or "conference call" in low)


def _is_right_company(text, company) -> bool:
    """Reject wrong-company matches (e.g. 'DBS' → Deutsche Bank): require a
    distinctive token in the header AND ≥3 mentions overall."""
    toks = _identity_tokens(company)
    low = text.lower()
    head = low[:3500]
    in_head = any(t in head for t in toks)
    best = max((low.count(t) for t in toks), default=0)
    return in_head and best >= 3


def _quarter_match(text, y, q) -> bool:
    low = text.lower()[:6000]
    short = str(y)[2:]
    ordinal = ["first", "second", "third", "fourth"][q - 1]
    pats = [f"q{q} {y}", f"q{q} {short}", f"{q}q{short}", f"{q}q {y}",
            f"{q}q'{short}", f"{ordinal} quarter {y}", f"{ordinal}-quarter {y}"]
    return any(p in low for p in pats)


# Transcript aggregators used when a company doesn't post the call on its own IR
# site (e.g. Goldman Sachs — found on Morningstar). Ordered by preference.
AGGREGATORS = ["morningstar.com", "fool.com", "insidermonkey.com",
               "seekingalpha.com", "tikr.com"]


def _aggregator_name(url: str) -> str:
    for dom, nm in (("morningstar", "Morningstar"), ("fool", "Motley Fool"),
                    ("insidermonkey", "Insider Monkey"),
                    ("seekingalpha", "Seeking Alpha"), ("tikr", "TIKR")):
        if dom in url:
            return nm
    return "Aggregator"


def _candidate_urls(company, y, q):
    """Ordered (url, source_name, confidence) candidates: IR site → aggregators
    (Morningstar/Fool/…) → broad web. Each tier is BUDGETED so the IR tier can't
    crowd out the aggregators (which often carry the full transcript)."""
    name = company["company"]
    ql = qlabel(y, q)
    ir = company.get("ir_domain")

    ir_urls = []
    if ir:
        for q_str in (f"{name} {ql} earnings call transcript filetype:pdf",
                      f"{name} {ql} earnings call transcript"):
            ir_urls += _search(q_str, include_domains=[ir])
    agg_urls = _search(f"{name} {ql} earnings call transcript",
                       include_domains=AGGREGATORS)
    broad_urls = _search(f"{name} {ql} earnings call transcript pdf")

    cands = []
    for u in dict.fromkeys(ir_urls[:4]):       # max 4 IR
        cands.append((u, "Investor Relations", CONFIDENCE["ir_transcript"]))
    for u in dict.fromkeys(agg_urls[:5]):      # max 5 aggregator
        cands.append((u, _aggregator_name(u), CONFIDENCE["web_scrape"]))
    for u in dict.fromkeys(broad_urls[:3]):    # max 3 broad
        cands.append((u, "Web", CONFIDENCE["web_scrape"]))
    return cands


def collect_one(company: dict, y: int, q: int):
    """Fetch the transcript for (company, quarter): IR site first, then
    aggregators. Validates the doc is the RIGHT company, and picks the BEST
    verified candidate (prefer quarter-matched, then longest, then most
    authoritative) rather than the first — so a full transcript beats a short
    press release / news blurb. Returns (text, source, url, confidence) or None.
    """
    best_key = None
    best = None
    seen = set()
    fetched = 0
    for url, sname, conf in _candidate_urls(company, y, q):
        if url in seen:
            continue
        seen.add(url)
        if fetched >= 10:
            break
        try:
            is_pdf = url.lower().endswith(".pdf")
            txt = _fetch_pdf_text(url) if is_pdf else _fetch_html_text(url)
        except Exception:
            continue
        fetched += 1
        if not (_looks_like_transcript(txt) and _is_right_company(txt, company)):
            continue
        wc = len(txt.split())
        qm = _quarter_match(txt, y, q)
        label = f"{sname} (PDF)" if is_pdf else sname
        eff_conf = conf if qm else round(conf - 0.15, 2)
        # early exit: a full IR/aggregator PDF for the right quarter is conclusive
        if is_pdf and qm and wc >= 8000:
            return txt, label, url, conf
        key = (1 if qm else 0, wc, conf)          # prefer quarter, length, source
        if best_key is None or key > best_key:
            best_key, best = key, (txt, label, url, eff_conf)
    return best


def _store_transcript(conn, run_id, company, ql, text, source_name, source_url, conf):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cldv_transcripts
                (company, country_iso, sector, quarter, transcript_text,
                 source_name, source_url, confidence_score, run_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company, quarter) DO UPDATE SET
                transcript_text = EXCLUDED.transcript_text,
                source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url,
                confidence_score = EXCLUDED.confidence_score, run_id = EXCLUDED.run_id,
                collected_at = now()
            """,
            (company["company"], company["country_iso"], company.get("sector"),
             ql, text, source_name, source_url, conf, run_id),
        )
    conn.commit()


def run_si1_transcripts(conn, run_id: str, n_quarters: int = 8):
    companies = active_companies()
    quarters = recent_quarters(n_quarters)
    cells = [(c, y, q) for c in companies for (y, q) in quarters]
    print(f"[SI1] collecting transcripts: {len(companies)} companies × "
          f"{n_quarters} quarters (newest {qlabel(*quarters[0])}) = {len(cells)} cells, "
          f"{_MAX_WORKERS} workers")

    lock = threading.Lock()
    ok = fail = 0

    def _cell(company, y, q):
        nonlocal ok, fail
        ql = qlabel(y, q)
        cconn = get_conn()
        try:
            res = collect_one(company, y, q)
            if res:
                txt, sname, surl, conf = res
                _store_transcript(cconn, run_id, company, ql, txt, sname, surl, conf)
                log_attempt(cconn, run_id, company["country_iso"],
                            f"transcript:{company['company']}:{ql}", sname, 1,
                            "success", source_url=surl)
                with lock:
                    ok += 1
                return True
            log_attempt(cconn, run_id, company["country_iso"],
                        f"transcript:{company['company']}:{ql}", "cascade", 1,
                        "failed", error_message="no transcript found")
            with lock:
                fail += 1
            return False
        except Exception as e:
            with lock:
                fail += 1
            return False
        finally:
            cconn.close()

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futs = [ex.submit(_cell, c, y, q) for (c, y, q) in cells]
        done = 0
        for _ in as_completed(futs):
            done += 1
            if done % 20 == 0:
                print(f"  [SI1] {done}/{len(cells)} cells ({ok} ok / {fail} miss)")

    print(f"[SI1] transcripts: {ok} collected / {fail} missed")
    return ok, fail
