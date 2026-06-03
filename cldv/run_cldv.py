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
    ap.add_argument("--only", choices=["si1", "si2", "si3", "scoring", "gap"],
                    help="run a single phase")
    args = ap.parse_args()

    if args.only == "gap":
        print_gap_report()
        return

    conn = get_conn()
    run_id = str(uuid.uuid4())
    register_run(conn, run_id, args.only or "full")
    print(f"=== CLDV run {run_id} (phase: {args.only or 'full'}) ===")

    total = succ = fail = gaps = 0

    if args.only in (None, "si3"):
        s, f, g = run_si3(conn, run_id)
        total += s + f; succ += s; fail += f; gaps += g

    if args.only in (None, "si1"):
        print("[SI1] corporate-displacement NLP — not yet implemented (Phase 2).")
    if args.only in (None, "si2"):
        print("[SI2] labor-market signal — not yet implemented (Phase 3).")

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
