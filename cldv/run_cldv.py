"""CLDV pipeline orchestrator.

Usage:
    python run_cldv.py                # collect (SI3 + SI1/SI2 when built) + score
    python run_cldv.py --only si3     # SI3 collection only
    python run_cldv.py --only scoring # re-score from existing raw metrics
    python run_cldv.py --only gap     # print the open-gap report
"""
import argparse
import uuid

from cldv_db import get_conn, register_run, finish_run
from cldv_si3_collectors import run_si3
from cldv_scoring import run_scoring
from cldv_gap_report import print_gap_report

# SI1 imports are lazy (heavy deps) — only loaded when SI1 runs.


def _print_final(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rank, country_iso, si1_corporate, si2_labor, si3_services, "
            "cldv_score FROM cldv_score_final "
            "WHERE run_id=(SELECT run_id FROM cldv_score_final "
            "ORDER BY scored_at DESC LIMIT 1) ORDER BY rank"
        )
        rows = cur.fetchall()
    if not rows:
        return
    print("\n  rank  country   SI1     SI2     SI3      CLDV")
    print("  " + "-" * 44)
    for rank, iso, si1, si2, si3, cldv in rows:
        f = lambda x: f"{x:6.2f}" if x is not None else "   –  "
        print(f"  {rank:>3}   {iso:<6}  {f(si1)}  {f(si2)}  {f(si3)}  {cldv:7.3f}")


def main():
    ap = argparse.ArgumentParser(description="CLDV pipeline")
    ap.add_argument("--only", choices=["si1", "si1-score", "si1-llm", "si1-judge",
                                       "si2", "si3", "scoring", "gap", "verify"],
                    help="run a single phase")
    ap.add_argument("--quarters", type=int, default=8,
                    help="SI1: number of recent quarters to collect (newest first)")
    args = ap.parse_args()

    if args.only == "gap":
        print_gap_report()
        return

    if args.only == "verify":
        import sys as _sys
        from cldv_verify import run_verify
        _sys.exit(run_verify())

    conn = get_conn()
    run_id = str(uuid.uuid4())
    register_run(conn, run_id, args.only or "full")
    print(f"=== CLDV run {run_id} (phase: {args.only or 'full'}) ===")

    total = succ = fail = gaps = 0

    if args.only in (None, "si3"):
        s, f, g = run_si3(conn, run_id)
        total += s + f; succ += s; fail += f; gaps += g

    if args.only in (None, "si1", "si1-score", "si1-llm", "si1-judge"):
        from cldv_si1_score import score_transcripts, aggregate_and_write_metrics
        from cldv_si1_llm import run_llm_scoring
        from cldv_si1_judge import run_llm_judge
        if args.only in (None, "si1"):
            from cldv_si1_transcripts import run_si1_transcripts
            ok, miss = run_si1_transcripts(conn, run_id, n_quarters=args.quarters)
            total += ok + miss; succ += ok; fail += miss
        if args.only in (None, "si1", "si1-score"):
            score_transcripts(conn, run_id)        # deterministic keyword baseline
        if args.only in (None, "si1", "si1-score", "si1-llm"):
            run_llm_scoring(conn, run_id)          # Claude contextual score (primary)
        run_llm_judge(conn, run_id)                # independent judge (verification)
        w, g = aggregate_and_write_metrics(conn, run_id)
        print(f"[SI1] {w} metrics written, {g} gaps")

    if args.only in (None, "si2"):
        from cldv_si2_collectors import run_si2
        s, f, g = run_si2(conn, run_id)
        total += s + f; succ += s; fail += f; gaps += g

    if args.only in (None, "scoring"):
        run_scoring(conn, run_id)
        _print_final(conn)

    finish_run(conn, run_id, total, succ, fail, gaps)
    if args.only in (None, "si3"):
        print(f"\n[run] {succ} stored / {fail} gaps")
        print_gap_report(conn)
    conn.close()


if __name__ == "__main__":
    main()
