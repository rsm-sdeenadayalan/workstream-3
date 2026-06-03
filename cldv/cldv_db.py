"""Shared DB config + datapoint/gap/log helpers for the CLDV pipeline.

Mirrors the WS1/WS2 storage contract: collectors build a datapoint dict via
`make_metric_result(...)` and persist it with `store_metric_datapoint(...)`;
each attempt is recorded with `log_attempt(...)`; unfilled cells call
`open_gap(...)`. All helpers commit per-call so they are safe to use from
independent per-thread connections.
"""
import os
import psycopg2
from datetime import date, datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.environ.get("POSTGRES_HOST", "localhost"),
    "port":     int(os.environ.get("POSTGRES_PORT", 5440)),
    "dbname":   os.environ.get("POSTGRES_DB", "cldv"),
    "user":     os.environ.get("POSTGRES_USER", ""),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
}

# 6 target countries (shared with WS1/WS2). iso3 = World Bank / UN code.
COUNTRIES = {
    "US": {"name": "United States",        "iso3": "USA"},
    "AE": {"name": "United Arab Emirates", "iso3": "ARE"},
    "BR": {"name": "Brazil",               "iso3": "BRA"},
    "IN": {"name": "India",                "iso3": "IND"},
    "SG": {"name": "Singapore",            "iso3": "SGP"},
    "PH": {"name": "Philippines",          "iso3": "PHL"},
}

# Confidence tiers by source type (0–1). Higher = more authoritative.
CONFIDENCE = {
    "worldbank_api":  0.90,   # official IGO statistical API
    "api_annual":     0.85,
    "file_download":  0.75,
    "ir_transcript":  0.80,   # company investor-relations primary source
    "web_scrape":     0.60,
    "research_agent": 0.55,
    "imputed":        0.30,
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)

# Alias kept for parity with WS1 naming; each thread should use its own conn.
_fresh_conn = get_conn


# ── Datapoint builder ────────────────────────────────────────────────────────
def make_metric_result(country_iso, sub_index, metric_key, metric_value, unit,
                        data_date, data_frequency, source_name, source_url,
                        access_method, confidence_score,
                        metric_label=None, raw_value=None) -> dict:
    return {
        "country_iso":      country_iso,
        "country_name":     COUNTRIES[country_iso]["name"],
        "sub_index":        sub_index,
        "metric_key":       metric_key,
        "metric_label":     metric_label,
        "metric_value":     metric_value,
        "unit":             unit,
        "data_date":        data_date,
        "data_frequency":   data_frequency,
        "source_name":      source_name,
        "source_url":       source_url,
        "access_method":    access_method,
        "confidence_score": confidence_score,
        "raw_value":        raw_value,
    }


# ── Persistence ──────────────────────────────────────────────────────────────
def store_metric_datapoint(conn, dp: dict, run_id: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cldv_raw_metrics
                (country_iso, country_name, sub_index, metric_key, metric_label,
                 metric_value, unit, data_date, data_frequency, source_name,
                 source_url, access_method, confidence_score, raw_value, run_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (country_iso, metric_key, data_date, source_name)
            DO UPDATE SET
                metric_value     = EXCLUDED.metric_value,
                confidence_score = EXCLUDED.confidence_score,
                source_url       = EXCLUDED.source_url,
                access_method    = EXCLUDED.access_method,
                raw_value        = EXCLUDED.raw_value,
                run_id           = EXCLUDED.run_id,
                collected_at     = now()
            """,
            (dp["country_iso"], dp["country_name"], dp["sub_index"],
             dp["metric_key"], dp.get("metric_label"), dp["metric_value"],
             dp.get("unit"), dp["data_date"], dp.get("data_frequency"),
             dp["source_name"], dp.get("source_url"), dp.get("access_method"),
             dp.get("confidence_score"), dp.get("raw_value"), run_id),
        )
    conn.commit()


def log_attempt(conn, run_id, country_iso, metric_key, collector_name, step,
                status, source_url=None, error_type=None, error_message=None,
                duration_ms=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cldv_collection_log
                (run_id, country_iso, metric_key, collector_name, step, status,
                 source_url, error_type, error_message, duration_ms)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (run_id, country_iso, metric_key, collector_name, step, status,
             source_url, error_type, (error_message or "")[:500], duration_ms),
        )
    conn.commit()


def open_gap(conn, country_iso, sub_index, metric_key, failure_reason,
             collectors_tried, severity="medium", metric_label=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cldv_data_gaps
                (country_iso, country_name, sub_index, metric_key, metric_label,
                 failure_reason, collectors_tried, severity)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (country_iso, metric_key) DO UPDATE SET
                attempt_count  = cldv_data_gaps.attempt_count + 1,
                failure_reason = EXCLUDED.failure_reason,
                last_attempted = now(),
                status         = 'open'
            """,
            (country_iso, COUNTRIES[country_iso]["name"], sub_index, metric_key,
             metric_label, (failure_reason or "")[:500],
             " | ".join(collectors_tried) if collectors_tried else None, severity),
        )
    conn.commit()


# ── Run bookkeeping ──────────────────────────────────────────────────────────
def register_run(conn, run_id, phase):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO cldv_runs (run_id, phase) VALUES (%s,%s) "
            "ON CONFLICT (run_id) DO NOTHING",
            (run_id, phase),
        )
    conn.commit()


def finish_run(conn, run_id, total, succeeded, failed, gaps, status="completed"):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cldv_runs SET finished_at=now(), total_tasks=%s, succeeded=%s,
                   failed=%s, gaps_opened=%s, status=%s WHERE run_id=%s
            """,
            (total, succeeded, failed, gaps, status, run_id),
        )
    conn.commit()
