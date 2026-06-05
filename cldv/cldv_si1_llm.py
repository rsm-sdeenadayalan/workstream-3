"""LLM-based contextual SI1 scoring + summarization (Anthropic Claude).

Deterministic keyword/TF-IDF counts phrases but cannot read CONTEXT - whether
"efficiency" is AI-driven displacement vs routine cost control, augmentation vs
replacement, or merely an analyst's question. This sends the AI/labor-relevant
excerpts of each transcript to Claude to (a) score the displacement signal in
context (-1..+1) and (b) summarize the company's AI-labor stance. The LLM score
becomes the PRIMARY SI1 signal; the keyword proxy_score is kept as a reproducible
cross-check (used as fallback when no LLM key is configured).

Public entry point: run_llm_scoring(conn, run_id) -> int (transcripts scored)
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from cldv_db import get_conn
from cldv_si1_dictionary import AI_TERMS, DISPLACEMENT, DISPLACEMENT_PROXY

try:
    import anthropic
except ImportError:
    anthropic = None

MODEL = os.environ.get("CLDV_LLM_MODEL", "claude-sonnet-4-6")
_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_MAX_WORKERS = max(1, int(os.environ.get("CLDV_MAX_WORKERS", "6")))
_TERMS = set(AI_TERMS + DISPLACEMENT + DISPLACEMENT_PROXY +
             ["headcount", "employees", "workforce", "efficiency", "hiring",
              "automation", "productivity", "restructuring"])

_PROMPT = """You are analyzing an earnings call for {company} ({quarter}).
Assess the AI-DRIVEN COGNITIVE-LABOR DISPLACEMENT signal from these excerpts ONLY.
Distinguish management statements from analyst questions; distinguish AI replacing
workers from AI augmenting workers or routine cost control.

Return STRICT JSON, no prose:
{{"displacement_score": <float -1..1>, "ai_attributed": <true|false>, "summary": "<1-2 sentence stance>", "evidence": "<exact sentence(s) quoted verbatim from the excerpts that justify the score; empty string if none>"}}

Scale: +1 = explicit AI/automation-driven workforce reduction; 0 = neutral / mixed /
insufficient signal; -1 = AI augmenting workers or net hiring.

EXCERPTS:
{excerpts}"""


def relevant_excerpts(text, window=220, max_chars=9000, max_hits=28):
    """Concatenate windows around AI/labor terms (keeps token cost bounded)."""
    if not text:
        return ""
    low = text.lower()
    starts = []
    for t in _TERMS:
        for m in re.finditer(r"(?<!\w)" + re.escape(t) + r"(?!\w)", low):
            starts.append(max(0, m.start() - window))
    starts = sorted(set(starts))[:max_hits]
    return "\n...\n".join(text[s:s + window * 2] for s in starts)[:max_chars]


def _parse(out):
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    if d.get("displacement_score") is None:
        return None
    return {"score": max(-1.0, min(1.0, float(d["displacement_score"]))),
            "ai": bool(d.get("ai_attributed")),
            "summary": (d.get("summary") or "")[:600],
            "evidence": (d.get("evidence") or "")[:1000]}


def score_with_claude(client, company, quarter, text):
    ex = relevant_excerpts(text)
    if len(ex) < 200:
        return None
    # temperature=0 for maximum determinism; retry on transient/rate-limit errors.
    last = None
    for attempt in range(4):
        try:
            r = client.messages.create(
                model=MODEL, max_tokens=400, temperature=0,
                messages=[{"role": "user",
                           "content": _PROMPT.format(company=company, quarter=quarter,
                                                     excerpts=ex)}])
            return _parse(r.content[0].text)
        except Exception as e:                       # rate limit / transient
            last = e
            if attempt == 3:
                break
            time.sleep(min(2 ** attempt, 10))
    raise last if last else RuntimeError("claude scoring failed")


def run_llm_scoring(conn, run_id: str, force: bool = False) -> int:
    """Score transcripts with Claude. By default CACHES - only transcripts
    without an llm_score are (re)scored, so re-runs are cheap and the stored
    scores are stable. Set force=True (or CLDV_LLM_FORCE=1) to re-score all."""
    if not (_KEY and anthropic):
        print("[SI1-LLM] no Anthropic key/SDK - keeping keyword scores")
        return 0
    force = force or os.environ.get("CLDV_LLM_FORCE", "").lower() in ("1", "true", "yes")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.company, t.quarter, t.transcript_text "
            "FROM cldv_transcripts t "
            "LEFT JOIN cldv_si1_company_scores s "
            "  ON s.company = t.company AND s.quarter = t.quarter "
            "WHERE t.transcript_text IS NOT NULL "
            "  AND (%s OR s.llm_score IS NULL)", (force,))
        rows = cur.fetchall()
    if not rows:
        print("[SI1-LLM] all transcripts already scored (cached) - nothing to do")
        return 0
    client = anthropic.Anthropic(api_key=_KEY)
    lock = threading.Lock()
    done = [0]
    failed = [0]

    def _one(company, quarter, text):
        cconn = get_conn()
        try:
            res = score_with_claude(client, company, quarter, text)
            if res:
                with cconn.cursor() as cur:
                    cur.execute(
                        "UPDATE cldv_si1_company_scores SET llm_score=%s, "
                        "llm_ai_attributed=%s, llm_summary=%s, llm_evidence=%s "
                        "WHERE company=%s AND quarter=%s",
                        (res["score"], res["ai"], res["summary"], res["evidence"],
                         company, quarter))
                cconn.commit()
                with lock:
                    done[0] += 1
        except Exception as e:
            with lock:
                failed[0] += 1
            print(f"  [SI1-LLM] FAILED {company} {quarter}: {type(e).__name__}")
        finally:
            cconn.close()

    print(f"[SI1-LLM] scoring {len(rows)} transcripts with {MODEL} "
          f"(temp=0, {_MAX_WORKERS} workers, cached)...")
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for _ in as_completed([ex.submit(_one, c, q, t) for c, q, t in rows]):
            pass
    print(f"[SI1-LLM] scored {done[0]}/{len(rows)} ({failed[0]} failed) with {MODEL}")
    return done[0]
