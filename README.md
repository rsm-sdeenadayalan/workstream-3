# Gramercy WS3 - CLDV (Cognitive Labor Displacement Velocity)

Measures, by country, the velocity at which AI is displacing cognitive labor across
6 countries (US, AE, BR, IN, SG, PH). Third index in the Gramercy capstone, alongside
WS1 (SDI) and WS2 (CII).

**CLDV = 0.40*SI1 + 0.35*SI2 + 0.25*SI3**

| Sub-index | Signal | Status |
|---|---|---|
| **SI1** (40%) | Corporate Displacement - NLP on earnings-call transcripts | implemented; US data (full collection pending) |
| **SI2** (35%) | Labor Market - ILOSTAT cognitive/AI-adjacent crossover ratio | implemented (all 6 countries) |
| **SI3** (25%) | Services Trade Flow - World Bank services-export trends | implemented (all 6 countries) |

Note: CLDV is reported **provisional** for any country missing a sub-index (the
scorer lists which sub-indices are present and excludes missing ones from the
weighted sum rather than redistributing weight).

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill POSTGRES_* (+ ANTHROPIC/TAVILY for SI1/agent)
.venv/bin/python cldv/setup_cldv.py     # create `cldv` DB + apply schema
```

## Usage
```bash
cd cldv
python run_cldv.py              # collect + score (full)
python run_cldv.py --only si3   # SI3 collection only
python run_cldv.py --only scoring
python run_cldv.py --only gap   # open-gap report
```

## Data sources (free only)
- **SI3:** World Bank WDI API (no key) - services exports, GDP, population, ICT-services
  share, services imports. Scored metric: currency-adjusted YoY change in services
  exports per capita (declining -> higher displacement).
- **SI1:** earnings-call transcripts via company IR PDFs (primary) + aggregators
  (Morningstar/Motley Fool/Insider Monkey); employee weights from SEC 10-K/20-F
  filings; deterministic two-track keyword/TF-IDF NLP.
  Each Claude score is grounded in quoted evidence and independently verified by a
  second model (LLM-as-judge); `cldv_verify` gates on >=80% scorer-vs-judge
  concordance. No human review pass.
- **SI2:** ILOSTAT employment-by-occupation (ISCO-08) cognitive(ISCO4)/AI-adjacent
  (ISCO2) crossover ratio - employment-stock proxy, documented limitations.

## Layout
```
cldv/   pipeline (run_cldv.py orchestrator, setup, schema, collectors, scoring, gaps)
tests/  pytest suite
docs/   CLDV_METHODOLOGY.md, specs/, plans/
```
Postgres DB `cldv` on the shared server (same host as WS1/WS2).
