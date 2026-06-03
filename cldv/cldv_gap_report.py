"""Summarize open data gaps, ordered by severity."""
from cldv_db import get_conn

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def print_gap_report(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT severity, sub_index, country_iso, metric_key, "
                "failure_reason, attempt_count FROM cldv_data_gaps "
                "WHERE status='open'"
            )
            rows = cur.fetchall()
        if not rows:
            print("[GAPS] none open ✓")
            return
        rows.sort(key=lambda r: (_SEV_ORDER.get(r[0], 9), r[1], r[2]))
        print(f"[GAPS] {len(rows)} open:")
        for sev, sub, iso, mk, reason, n in rows:
            print(f"  [{sev:6s}] {sub} {iso} {mk} (x{n}) — {reason}")
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    print_gap_report()
