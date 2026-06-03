# CLDV (Workstream 3) - Client Quickstart

Cognitive Labor Displacement Velocity index for 6 countries (US, AE, BR, IN, SG, PH).
See `docs/CLDV_METHODOLOGY.md` for the full methodology.

## 1. Prerequisites
- Python 3.11+ and PostgreSQL (the shared Gramercy server, `localhost:5440`).
- A Tavily API key (free tier, 1000 searches/month) for SI1 transcript discovery.
  SI2 and SI3 need no keys.

## 2. Setup (about 5 minutes)
```bash
git clone git@github.com:rsm-sdeenadayalan/workstream-3.git
cd workstream-3
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill POSTGRES_* and TAVILY_API_KEY
.venv/bin/python cldv/setup_cldv.py     # create the `cldv` database + schema
```

## 3. Run
```bash
cd cldv
python run_cldv.py --only si3      # World Bank services-trade  (no key, ~30s)
python run_cldv.py --only si2      # ILOSTAT labor market       (no key, ~30s)
python run_cldv.py --only si1      # transcript NLP + headcount (Tavily; long)
python run_cldv.py --only scoring  # normalize + composite CLDV
python run_cldv.py --only gap      # open-gap report
python run_cldv.py                 # full pipeline
```
`--quarters N` controls how many recent quarters SI1 collects (default 8). A full
SI1 run is roughly 4 searches x 37 companies x N quarters - size N to your Tavily
budget.

## 4. Read the results
```sql
-- final composite + sub-index scores
SELECT * FROM v_cldv_latest_scores;
-- any metric traced to its source
SELECT * FROM v_cldv_provenance WHERE country_iso = 'US';
-- latest raw value per (country, metric)
SELECT * FROM v_cldv_raw_latest;
```

## 5. Key tables
| Table | Contents |
|---|---|
| `cldv_raw_metrics` | every raw datapoint (value, date, source_name, source_url, raw_value computation) |
| `cldv_transcripts` | earnings-call transcripts (text + working URL) |
| `cldv_si1_company_scores` | per-company-quarter NLP scores |
| `cldv_si1_headcount` | employee weights from SEC filings (dated + sourced) |
| `cldv_score_final` | composite CLDV + rank |
| `cldv_data_gaps` | documented open gaps by severity |

## 6. Notes / gotchas
- **Provisional CLDV:** if a sub-index has no data for a country (e.g. SI1 before
  a full collection), the scorer flags the composite provisional and excludes the
  missing sub-index (it does not redistribute its weight).
- **Methodology weights are in the DB** (`cldv_score_methodology`,
  `cldv_subindex_weights`) - change them without touching code, then re-run
  `--only scoring`.
- **SI1 validation:** the 2-reviewer 80%-concordance pass over transcript
  excerpts must be run before SI1 scores are published (see methodology SI1).
- **SI2 caveat:** the crossover ratio is an ILOSTAT employment-stock proxy
  (no free job-postings source); documented in the methodology.
