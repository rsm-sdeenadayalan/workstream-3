-- ============================================================================
-- Gramercy WS3 — CLDV (Cognitive Labor Displacement Velocity) schema
-- Idempotent: safe to re-run. Mirrors the WS1/WS2 layered design:
--   collection → scoring → output → operational, plus config + views.
-- ============================================================================
BEGIN;

-- ── Config: methodology weights (externalized so formulas change w/o code) ───
CREATE TABLE IF NOT EXISTS cldv_subindex_weights (
    sub_index   TEXT PRIMARY KEY,         -- 'SI1' | 'SI2' | 'SI3'
    label       TEXT NOT NULL,
    weight      NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS cldv_score_methodology (
    sub_index   TEXT NOT NULL,
    metric_key  TEXT NOT NULL,
    metric_label TEXT,
    weight      NUMERIC NOT NULL DEFAULT 0,   -- weight WITHIN the sub-index
    invert      BOOLEAN NOT NULL DEFAULT FALSE,-- TRUE: low raw value → high score
    scored      BOOLEAN NOT NULL DEFAULT TRUE, -- FALSE: collected as context only
    PRIMARY KEY (sub_index, metric_key)
);

-- ── Collection: one row per (country, metric, data_date, source) ─────────────
CREATE TABLE IF NOT EXISTS cldv_raw_metrics (
    id              SERIAL PRIMARY KEY,
    country_iso     TEXT NOT NULL,
    country_name    TEXT,
    sub_index       TEXT NOT NULL,
    metric_key      TEXT NOT NULL,
    metric_label    TEXT,
    metric_value    NUMERIC,
    unit            TEXT,
    data_date       DATE NOT NULL,
    data_frequency  TEXT,
    source_name     TEXT NOT NULL,
    source_url      TEXT,
    access_method   TEXT,
    confidence_score NUMERIC,
    raw_value       TEXT,
    is_imputed      BOOLEAN NOT NULL DEFAULT FALSE,
    run_id          TEXT,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (country_iso, metric_key, data_date, source_name)
);
CREATE INDEX IF NOT EXISTS ix_cldv_raw_country_metric
    ON cldv_raw_metrics (country_iso, metric_key, data_date DESC);

-- ── SI1 corpus: raw earnings-call transcripts (populated in Phase 2) ─────────
CREATE TABLE IF NOT EXISTS cldv_transcripts (
    id              SERIAL PRIMARY KEY,
    company         TEXT NOT NULL,
    country_iso     TEXT NOT NULL,
    sector          TEXT,
    quarter         TEXT NOT NULL,            -- e.g. '2025Q1'
    transcript_text TEXT,
    source_name     TEXT,
    source_url      TEXT,
    confidence_score NUMERIC,
    run_id          TEXT,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company, quarter)
);

-- ── Operational: runs, attempt log, gaps ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS cldv_runs (
    run_id       TEXT PRIMARY KEY,
    phase        TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    total_tasks  INTEGER,
    succeeded    INTEGER,
    failed       INTEGER,
    gaps_opened  INTEGER,
    status       TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS cldv_collection_log (
    id            SERIAL PRIMARY KEY,
    run_id        TEXT,
    country_iso   TEXT,
    metric_key    TEXT,
    collector_name TEXT,
    step          INTEGER,
    status        TEXT,                       -- success | failed | no_data_in_source
    source_url    TEXT,
    error_type    TEXT,
    error_message TEXT,
    duration_ms   INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cldv_data_gaps (
    id            SERIAL PRIMARY KEY,
    country_iso   TEXT NOT NULL,
    country_name  TEXT,
    sub_index     TEXT,
    metric_key    TEXT NOT NULL,
    metric_label  TEXT,
    failure_reason TEXT,
    collectors_tried TEXT,
    severity      TEXT NOT NULL DEFAULT 'medium',
    attempt_count INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'open',
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attempted TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (country_iso, metric_key)
);

-- ── Scoring + output ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cldv_score_metric_normalized (
    run_id        TEXT NOT NULL,
    country_iso   TEXT NOT NULL,
    sub_index     TEXT NOT NULL,
    metric_key    TEXT NOT NULL,
    raw_value     NUMERIC,
    normalized    NUMERIC,                    -- 0–100
    invert        BOOLEAN,
    weight        NUMERIC,
    weighted_score NUMERIC,
    PRIMARY KEY (run_id, country_iso, sub_index, metric_key)
);

CREATE TABLE IF NOT EXISTS cldv_score_subindex (
    run_id        TEXT NOT NULL,
    country_iso   TEXT NOT NULL,
    sub_index     TEXT NOT NULL,
    subindex_score NUMERIC,                   -- 0–100
    weight        NUMERIC,
    weighted_score NUMERIC,
    PRIMARY KEY (run_id, country_iso, sub_index)
);

CREATE TABLE IF NOT EXISTS cldv_score_final (
    run_id        TEXT NOT NULL,
    country_iso   TEXT NOT NULL,
    country_name  TEXT,
    si1_corporate NUMERIC,
    si2_labor     NUMERIC,
    si3_services  NUMERIC,
    cldv_score    NUMERIC,                    -- 0–100
    rank          INTEGER,
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, country_iso)
);

-- ── Views: latest snapshot ───────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_cldv_latest_scores AS
SELECT f.*
FROM cldv_score_final f
JOIN (SELECT run_id, MAX(scored_at) AS m FROM cldv_score_final GROUP BY run_id) x
  ON f.run_id = x.run_id
WHERE f.scored_at = (SELECT MAX(scored_at) FROM cldv_score_final)
ORDER BY f.rank;

CREATE OR REPLACE VIEW v_cldv_raw_latest AS
SELECT DISTINCT ON (country_iso, metric_key)
       country_iso, country_name, sub_index, metric_key, metric_label,
       metric_value, unit, data_date, source_name, confidence_score, run_id
FROM cldv_raw_metrics
ORDER BY country_iso, metric_key, data_date DESC, confidence_score DESC NULLS LAST;

COMMIT;

-- ── Seed: sub-index weights (per spec) ───────────────────────────────────────
INSERT INTO cldv_subindex_weights (sub_index, label, weight) VALUES
    ('SI1', 'Corporate Displacement Signal', 0.40),
    ('SI2', 'Labor Market Signal',           0.35),
    ('SI3', 'Services Trade Flow Signal',    0.25)
ON CONFLICT (sub_index) DO UPDATE
    SET label = EXCLUDED.label, weight = EXCLUDED.weight;

-- ── Seed: SI3 methodology (spec-literal — only per-capita rate-of-change is scored) ──
INSERT INTO cldv_score_methodology (sub_index, metric_key, metric_label, weight, invert, scored) VALUES
    ('SI3', 'services_exports_per_capita_yoy', 'Services exports per capita, YoY % change', 1.00, TRUE,  TRUE),
    ('SI3', 'services_exports_per_capita',     'Services exports per capita (USD)',          0.00, FALSE, FALSE),
    ('SI3', 'services_exports_pct_gdp',        'Services exports (% of GDP)',                0.00, FALSE, FALSE),
    ('SI3', 'it_bpo_export_growth_yoy',        'IT/BPO services export growth (YoY %)',      0.00, FALSE, FALSE),
    ('SI3', 'current_account_services_balance','Current-account services balance (USD)',     0.00, FALSE, FALSE)
ON CONFLICT (sub_index, metric_key) DO UPDATE
    SET metric_label = EXCLUDED.metric_label, weight = EXCLUDED.weight,
        invert = EXCLUDED.invert, scored = EXCLUDED.scored;
