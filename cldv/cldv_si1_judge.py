"""LLM-as-judge ensemble for SI1 - independent verification of the Claude
contextual score, replacing the spec's human 2-reviewer concordance step.

The scorer (cldv_si1_llm) grounds each score in verbatim quoted evidence. This
module sends the same excerpts PLUS the scorer's score/summary/evidence to a
SECOND, INDEPENDENT model (CLDV_JUDGE_MODEL, default a different/stronger model
than the scorer) which:
  (a) independently re-scores the displacement signal (-1..+1) from the excerpts
      alone, and
  (b) rules whether the scorer's score is JUSTIFIED by its cited evidence.

Directional agreement (scorer vs judge) + the justified-rate become an automated
concordance metric (cldv_si1_validate concordance) that gates publication via
cldv_verify - no humans required.

Public entry point: run_llm_judge(conn, run_id) -> int (rows judged)
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from cldv_db import get_conn
from cldv_si1_llm import relevant_excerpts

try:
    import anthropic
except ImportError:
    anthropic = None

# A DIFFERENT model than the scorer (claude-sonnet-4-6) so concordance is a real
# cross-check rather than a model agreeing with itself. Opus 4.5 is a strong,
# independent auditor that still accepts temperature=0 (Opus 4.7/4.8 reject
# sampling params with a 400), so judge_one reuses the scorer's call pattern.
JUDGE_MODEL = os.environ.get("CLDV_JUDGE_MODEL", "claude-opus-4-5")
_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_MAX_WORKERS = max(1, int(os.environ.get("CLDV_MAX_WORKERS", "6")))

_PROMPT = """You are an INDEPENDENT auditor of an AI-labor displacement score for {company} ({quarter}).
A first model scored the earnings-call excerpts below. Do TWO things:

1. INDEPENDENTLY score the AI-DRIVEN COGNITIVE-LABOR DISPLACEMENT signal from the
   EXCERPTS ONLY - ignore the first model's number. Scale: +1 = explicit
   AI/automation-driven workforce reduction; 0 = neutral / mixed / insufficient;
   -1 = AI augmenting workers or net hiring.
2. JUDGE whether the FIRST MODEL'S score is JUSTIFIED by the evidence it cited.
   It is NOT justified if the cited evidence is absent from the excerpts, is an
   analyst question mistaken for management guidance, or conflates routine cost
   control / augmentation with AI-driven replacement.

Return STRICT JSON, no prose:
{{"judge_score": <float -1..1>, "justified": <true|false>, "rationale": "<=1 sentence"}}

FIRST MODEL score: {scorer_score}
FIRST MODEL summary: {scorer_summary}
FIRST MODEL cited evidence: {scorer_evidence}

EXCERPTS:
{excerpts}"""


def _parse_judge(out):
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    if d.get("judge_score") is None:
        return None
    try:
        score = max(-1.0, min(1.0, float(d["judge_score"])))
    except (ValueError, TypeError):
        return None
    return {"score": score,
            "justified": bool(d.get("justified")),
            "rationale": (d.get("rationale") or "")[:600]}


def judge_one(client, company, quarter, text, scorer_score, scorer_summary, scorer_evidence):
    ex = relevant_excerpts(text)
    if len(ex) < 200:
        return None
    last = None
    for attempt in range(4):
        try:
            r = client.messages.create(
                model=JUDGE_MODEL, max_tokens=400, temperature=0,
                messages=[{"role": "user",
                           "content": _PROMPT.format(
                               company=company, quarter=quarter,
                               scorer_score=scorer_score,
                               scorer_summary=scorer_summary or "",
                               scorer_evidence=scorer_evidence or "",
                               excerpts=ex)}])
            return _parse_judge(r.content[0].text)
        except Exception as e:                       # rate limit / transient
            last = e
            if attempt == 3:
                break
            time.sleep(min(2 ** attempt, 10))
    raise last if last else RuntimeError("claude judge failed")


def run_llm_judge(conn, run_id: str, force: bool = False) -> int:
    """Judge every Claude-scored transcript with an independent model. CACHES by
    default - only rows without a judge_score are (re)judged, so re-runs are cheap
    and verdicts are stable. force=True (or CLDV_JUDGE_FORCE=1) re-judges all."""
    if not (_KEY and anthropic):
        print("[SI1-JUDGE] no Anthropic key/SDK - skipping judge pass")
        return 0
    force = force or os.environ.get("CLDV_JUDGE_FORCE", "").lower() in ("1", "true", "yes")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.company, s.quarter, t.transcript_text, s.llm_score, "
            "       s.llm_summary, s.llm_evidence "
            "FROM cldv_si1_company_scores s "
            "JOIN cldv_transcripts t ON t.company=s.company AND t.quarter=s.quarter "
            "WHERE s.llm_score IS NOT NULL AND t.transcript_text IS NOT NULL "
            "  AND (%s OR s.judge_score IS NULL)", (force,))
        rows = cur.fetchall()
    if not rows:
        print("[SI1-JUDGE] all scored transcripts already judged (cached) - nothing to do")
        return 0
    client = anthropic.Anthropic(api_key=_KEY)
    lock = threading.Lock()
    done = [0]
    failed = [0]

    def _one(company, quarter, text, sc, summ, evid):
        cconn = get_conn()
        try:
            res = judge_one(client, company, quarter, text, sc, summ, evid)
            if res:
                with cconn.cursor() as cur:
                    cur.execute(
                        "UPDATE cldv_si1_company_scores SET judge_score=%s, "
                        "judge_justified=%s, judge_rationale=%s, judge_model=%s "
                        "WHERE company=%s AND quarter=%s",
                        (res["score"], res["justified"], res["rationale"],
                         JUDGE_MODEL, company, quarter))
                cconn.commit()
                with lock:
                    done[0] += 1
        except Exception as e:
            with lock:
                failed[0] += 1
            print(f"  [SI1-JUDGE] FAILED {company} {quarter}: {type(e).__name__}")
        finally:
            cconn.close()

    print(f"[SI1-JUDGE] judging {len(rows)} scored transcripts with {JUDGE_MODEL} "
          f"(temp=0, {_MAX_WORKERS} workers, cached)...")
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for _ in as_completed([ex.submit(_one, *r) for r in rows]):
            pass
    print(f"[SI1-JUDGE] judged {done[0]}/{len(rows)} ({failed[0]} failed) with {JUDGE_MODEL}")
    return done[0]
