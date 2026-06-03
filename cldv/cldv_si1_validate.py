"""SI1 validation harness (the spec's 2-reviewer 80%-concordance step).

  export  -> writes a review pack CSV: one row per scored transcript with an
             excerpt + the model's keyword and Claude labels + a blank
             `human_label` column for two independent reviewers to fill
             (displacement / neutral / augmentation).
  ingest  -> reads a filled review pack and reports concordance between the human
             label and each model (Claude, keyword); target >= 80%.
  agree   -> automated keyword-vs-Claude directional agreement across all scored
             transcripts (a first-pass quality signal, no humans needed).

Usage:
  python cldv/cldv_si1_validate.py export reviews.csv
  python cldv/cldv_si1_validate.py ingest reviews.csv
  python cldv/cldv_si1_validate.py agree
"""
import csv
import sys

from cldv_db import get_conn
from cldv_si1_llm import relevant_excerpts

_NEUTRAL_BAND = 0.1


def label(score):
    if score is None:
        return ""
    s = float(score)
    if s > _NEUTRAL_BAND:
        return "displacement"
    if s < -_NEUTRAL_BAND:
        return "augmentation"
    return "neutral"


def export_review_pack(path, n=50):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.company, s.quarter, s.proxy_score, s.llm_score, "
            "s.llm_ai_attributed, s.llm_summary, t.transcript_text "
            "FROM cldv_si1_company_scores s "
            "JOIN cldv_transcripts t ON t.company=s.company AND t.quarter=s.quarter "
            "ORDER BY s.company, s.quarter LIMIT %s", (n,))
        rows = cur.fetchall()
    conn.close()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "quarter", "excerpt", "keyword_label", "claude_label",
                    "claude_ai_attributed", "claude_summary",
                    "human_label (displacement/neutral/augmentation)", "human_notes"])
        for company, quarter, proxy, llm, ai, summary, text in rows:
            ex = relevant_excerpts(text, max_chars=1200, max_hits=4).replace("\n", " ")
            w.writerow([company, quarter, ex, label(proxy), label(llm), ai,
                        summary, "", ""])
    print(f"wrote {len(rows)} rows to {path} - have 2 reviewers fill human_label")


def _concordance(pairs):
    if not pairs:
        return 0.0, 0
    agree = sum(1 for a, b in pairs if a == b)
    return agree / len(pairs), len(pairs)


def ingest(path):
    rows = list(csv.DictReader(open(path)))
    human_key = next((k for k in rows[0] if k.startswith("human_label")), None) if rows else None
    vs_claude, vs_keyword = [], []
    for r in rows:
        h = (r.get(human_key) or "").strip().lower()
        if h not in ("displacement", "neutral", "augmentation"):
            continue
        vs_claude.append((h, (r.get("claude_label") or "").strip().lower()))
        vs_keyword.append((h, (r.get("keyword_label") or "").strip().lower()))
    c, n = _concordance(vs_claude)
    k, _ = _concordance(vs_keyword)
    print(f"human-labeled rows: {n}")
    print(f"  human vs Claude  concordance: {c*100:.1f}%  ({'PASS' if c>=0.8 else 'BELOW 80%'})")
    print(f"  human vs keyword concordance: {k*100:.1f}%")


def agree():
    """Automated keyword-vs-Claude directional agreement (no humans)."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT proxy_score, llm_score FROM cldv_si1_company_scores "
                    "WHERE proxy_score IS NOT NULL AND llm_score IS NOT NULL")
        rows = cur.fetchall()
    conn.close()
    pairs = [(label(p), label(l)) for p, l in rows]
    a, n = _concordance(pairs)
    print(f"keyword vs Claude directional agreement: {a*100:.1f}% over {n} transcripts")
    print("(low agreement is expected - it quantifies how much contextual scoring "
          "changes vs naive keyword counting, motivating the human validation pass)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "agree"
    if cmd == "export":
        export_review_pack(sys.argv[2] if len(sys.argv) > 2 else "reviews.csv")
    elif cmd == "ingest":
        ingest(sys.argv[2])
    else:
        agree()
