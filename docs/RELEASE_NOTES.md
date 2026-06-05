# CLDV - Release Notes

## v0.1.0 (2026-06-02)

First tagged edition of Workstream 3 - the **Cognitive Labor Displacement
Velocity (CLDV)** index. All three sub-indices are implemented, traceable, and
produce a composite score for the six target countries. This is a v0.1 (pre-1.0)
edition: the engineering is production-grade, but two operational steps remain
before a published-production index (see "Path to v1.0").

```
CLDV = 0.40 * SI1 (Corporate Displacement)
     + 0.35 * SI2 (Labor Market)
     + 0.25 * SI3 (Services Trade Flow)
```
Countries: US, AE, BR, IN, SG, PH.

---

### What is included

| Sub-index | Signal | Source (free, primary) | Coverage |
|---|---|---|---|
| SI1 (0.40) | Corporate displacement language | Earnings transcripts (IR/aggregators) scored by Claude; employee weights from SEC 10-K/20-F | 6/6 countries; 86 transcripts, 4 quarters |
| SI2 (0.35) | Cognitive vs AI-adjacent labor shift | ILOSTAT employment-by-occupation (ISCO-08) | 6/6 countries |
| SI3 (0.25) | Services-export trends | World Bank WDI | 6/6 countries |

**Composite snapshot (v0.1 dataset; SI1 partial corpus):**

| Rank | Country | SI1 | SI2 | SI3 | CLDV |
|---|---|---|---|---|---|
| 1 | BR | 100.0 | 97.3 | 70.2 | 91.6 |
| 2 | PH | 28.6 | 94.1 | 87.6 | 66.2 |
| 3 | IN | 49.6 | 88.7 | 17.0 | 55.2 |
| 4 | SG | 42.6 | 100.0 | 0.0 | 52.0 |
| 5 | AE | 53.8 | 0.0 | 100.0 | 46.5 |
| 6 | US | 0.0 | 82.2 | 26.8 | 35.5 |

Scores are a v0.1 snapshot and will move once the full SI1 corpus is collected
and the SI1 judge-ensemble concordance pass is run across it.

---

### Production-grade properties

- **Primary sourcing** - World Bank, ILOSTAT, SEC EDGAR filings, company IR. No
  secondary aggregators where a primary exists.
- **Full provenance** - every raw data point carries a working source URL and the
  exact computation; the `v_cldv_provenance` view joins any metric to its
  source(s); derived scores reproduce via `run_id -> cldv_raw_metrics -> URLs`.
- **Dating** - every value is stamped with the period it represents; collectors
  resolve to the newest figure each source publishes.
- **AI where it adds value** - Claude (`claude-sonnet-4-6`) scores displacement in
  context and summarizes each call; keyword/TF-IDF kept as a reproducible
  cross-check and fallback.
- **Reproducibility** - LLM scoring is `temperature=0` and content-cached, with
  retry/backoff; re-runs do not re-call and stored scores are stable.
- **QA gate** - `cldv_verify.py` fails (exit 1) on structural violations (weights
  not summing to 1, scores out of range, non-contiguous ranks, missing
  provenance) and warns on data-quality signals (coverage gaps, YoY outliers).
- **Tested + CI** - 26 unit tests; GitHub Actions runs `pytest` on every push.
- **Config-as-data** - methodology weights live in DB tables, changeable without
  code edits.

---

### Architecture

```
cldv/
  run_cldv.py            orchestrator: --only {si1,si1-score,si1-llm,si2,si3,scoring,gap,verify}
  setup_cldv.py          idempotent DB bootstrap + schema
  cldv_schema.sql        tables, views, seeded methodology weights
  cldv_si3_collectors.py World Bank services-trade
  cldv_si2_collectors.py ILOSTAT crossover ratio
  cldv_si1_transcripts.py transcript collection (IR-primary, verified)
  cldv_si1_llm.py        Claude contextual scoring + summaries (primary)
  cldv_si1_nlp.py        deterministic keyword/TF-IDF (cross-check)
  cldv_si1_headcount.py  SEC-filing headcount (employment weights)
  cldv_si1_score.py      aggregation -> QoQ velocity
  cldv_scoring.py        normalize 0-100 + composite
  cldv_verify.py         QA gate
  cldv_si1_judge.py      independent LLM judge (re-score + justification)
  cldv_si1_validate.py   automated scorer-vs-judge concordance report
tests/                   26 pytest tests
docs/                    CLDV_METHODOLOGY.md, RELEASE_NOTES.md
```
See `CLIENT_QUICKSTART.md` to run; `docs/CLDV_METHODOLOGY.md` for the methodology.

---

### Known limitations

- **SI1 corpus is partial** - 86 transcripts over 4 quarters; some emerging-market
  firms are thin (AE/PH ~2 firms). A full Q1-2023 collection is pending.
- **SI1 validation is LLM-ensemble, not human** - each score is grounded in
  quoted evidence and independently re-scored by a second model
  (`claude-opus-4-5`); `cldv_verify` fails below 80% scorer-vs-judge concordance.
  No human review pass is used.
- **SI2 is an employment-stock proxy** - ILOSTAT ISCO-08 (1-digit), not job
  postings (no free historical postings source exists).
- **No scheduled refresh / live monitoring.**

### Path to v1.0
1. Run the SI1 judge ensemble across the full corpus; confirm >=80% scorer-vs-judge
   concordance (`cldv/run_cldv.py --only si1-judge` then `--only verify`).
2. Full Q1-2023 -> latest SI1 collection across all firms.
3. Optional: source a finer occupational series for SI2; add scheduled refresh.

---

### Reproduce
```bash
python cldv/setup_cldv.py
python cldv/run_cldv.py --only si3
python cldv/run_cldv.py --only si2
python cldv/run_cldv.py --only si1        # needs Tavily + Anthropic keys
python cldv/run_cldv.py --only scoring
python cldv/run_cldv.py --only verify
```
Repository: https://github.com/rsm-sdeenadayalan/workstream-3
