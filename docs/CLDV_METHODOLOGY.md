# CLDV - Cognitive Labor Displacement Velocity: Methodology

**Workstream 3 of the Gramercy capstone.** Measures, by country, the velocity at
which AI is displacing cognitive labor, from three independent signals:

```
CLDV = 0.40 * SI1 (Corporate Displacement)
     + 0.35 * SI2 (Labor Market)
     + 0.25 * SI3 (Services Trade Flow)
```

**Countries (6):** United States (US), United Arab Emirates (AE), Brazil (BR),
India (IN), Singapore (SG), Philippines (PH).

**Design principles**
- **Free sources only** - no paid data subscriptions.
- **Primary sources first** - company filings/IR over aggregators; official
  statistical APIs over secondary trackers.
- **Latest data** - every collector resolves to the newest figure its source
  publishes.
- **Full provenance** - every raw data point carries a working source URL, the
  date it represents, and (for computed metrics) the exact computation.

---

## SI1 - Corporate Displacement Signal (weight 0.40)

Intensity and trajectory of AI-related workforce-reduction language in earnings
calls for ~37 companies across the 6 countries.

### Corpus
Earnings-call transcripts, newest quarter first. Source cascade per
(company, quarter):
1. **Company investor-relations PDF** (primary - authoritative, freshest).
2. **Transcript aggregators** - Morningstar, Motley Fool, Insider Monkey,
   Seeking Alpha (e.g. Goldman Sachs publishes its call on Motley Fool, not IR).
3. **Broad web** (last resort).

Every candidate is verified to be the **right company** (distinctive name/ticker
tokens in the header + frequency) and the **right quarter**; the longest,
most-authoritative quarter-matched transcript wins. Stored in `cldv_transcripts`
with its working URL.

### Scoring - two-track NLP (deterministic)
Real calls (especially banks) express displacement as "efficiency" without
naming AI, so two scores are computed per transcript:

- **proxy_score (primary)** - efficiency / headcount-reduction language,
  amplified when AI/automation terms co-occur in the call.
- **strict_score (cross-check)** - displacement counted only when AI is
  explicitly attributed.

Both use the spec formula, with TF-IDF weighting across the corpus:
```
displacement_score = tanh( (displacement_density - augmentation_density)
                           x investment_to_hiring_ratio x ai_context / k )    in  [-1, +1]
```
Densities are per-1,000-words over four keyword categories (displacement,
augmentation, investment, hiring); negated hits are discounted. The versioned
dictionary lives in `cldv_si1_dictionary.py` and is expanded during validation.

### Aggregation
Company scores are aggregated to country level **weighted by employee headcount**,
pulled from the latest **SEC 10-K / 20-F filing** (primary source; dated by
filing period; web-aggregator fallback for non-SEC filers). The **quarter-over-
quarter change** in the country score is the **velocity** - the scored SI1
metric (`corporate_displacement_velocity`).

### Validation (required before publication)
Two reviewers independently classify >=50 transcript excerpts; the harness reports
concordance against the model (target >=80%); missed signals and false positives
update the dictionary. *This human step is pending for the full corpus.*

### Limitations
- AI-attribution is sparse in some sectors - the proxy track mitigates this; the
  strict track is reported alongside.
- Mubadala (diffuse holding co) and Accenture-Philippines (not separable from
  global Accenture) are dropped/substituted - documented gaps.

---

## SI2 - Labor Market Signal (weight 0.35)

The spec's job-posting "crossover ratio" has **no free historical source**
(LinkedIn/Lightcast/Revelio are paid). We use an **employment-stock proxy** from
**ILOSTAT** (ILO, free, no key) employment-by-occupation, ISCO-08:

- **Cognitive labor (automatable):** ISCO 4 - clerical support workers
  (data entry, back-office, admin).
- **AI-adjacent (growing):** ISCO 2 - professionals, including ICT professionals.

```
crossover_ratio        = employment(ISCO 4) / employment(ISCO 2)
crossover_ratio_yoy    = YoY % change of the ratio        <- scored (inverted)
```
A **falling** ratio (cognitive labor shrinking relative to AI-adjacent roles) is
a displacement signal, so `crossover_ratio_yoy` is **inverted** in scoring.
Component YoY series (`cognitive_labor_yoy`, `ai_adjacent_yoy`) are tracked as
context.

### Limitations
- ISCO 1-digit groups are coarse - some at-risk cognitive roles (analysts,
  accountants) sit in ISCO 2 alongside AI-adjacent professionals.
- Employment **stock**, not job **postings** - a structural proxy for the
  intended demand signal. This is the sub-index most constrained by the
  free-data requirement.

---

## SI3 - Services Trade Flow Signal (weight 0.25)

Macro confirmation via services-export trends, entirely from the **World Bank
WDI** API (free, no key). USD-denominated (currency-comparable by construction).

| Metric | Definition | Scored |
|---|---|---|
| services_exports_per_capita_yoy | YoY % change of services exports / population | **yes (inverted)** |
| services_exports_per_capita | services exports / population (level) | context |
| services_exports_pct_gdp | services exports / GDP | context |
| it_bpo_export_growth_yoy | ICT-services export value (ICT % x services exports), YoY | context |
| current_account_services_balance | services exports - imports | context |

Per the spec, the scored signal is the currency-adjusted **rate of change of
services exports per capita** - declining exports indicate displacement, so it is
**inverted**. World Bank annual data lags ~1 year (latest = 2024).

---

## Scoring

Configuration lives in DB tables (`cldv_score_methodology`,
`cldv_subindex_weights`) so weights change without code edits.

1. **Selection** - confidence-first, then most-recent value per (country, metric).
2. **Normalization** - min-max to **0-100** across the 6 countries per metric;
   `invert` flips metrics where a lower raw value means more displacement;
   all-equal -> 50.
3. **Sub-index** - weighted sum of its scored metrics (missing data contributes
   0; weight is not redistributed).
4. **Composite** - `CLDV = 0.40*SI1 + 0.35*SI2 + 0.25*SI3`, ranked 1-6. A
   sub-index with no data yet is excluded and the result is flagged
   **provisional**.

---

## Provenance & dating

Every raw data point is dated (`data_date` = the period it represents) and
resolves to a working source:
- **SI3** -> the exact World Bank API URL returning the value + the computation.
- **SI2** -> the exact ILOSTAT API URL + the computation.
- **SI1** -> the transcript URL(s) (level/velocity list every contributing call)
  and the SEC filing URL for each headcount weight.

The `v_cldv_provenance` view joins any metric to its source(s). Derived scores
are reproducible via `run_id -> cldv_raw_metrics -> source URLs`.

---

## Data sources (all free)

| Sub-index | Source | Key? | Latency |
|---|---|---|---|
| SI1 transcripts | Company IR / Morningstar / Motley Fool / Insider Monkey | no | days |
| SI1 headcount | SEC EDGAR 10-K/20-F (primary); web aggregators (fallback) | no | annual filing |
| SI2 | ILOSTAT EMP_TEMP_SEX_OCU_NB (ISCO-08) | no | ~annual |
| SI3 | World Bank WDI (BX.GSR.NFSV.CD, NY.GDP.MKTP.CD, SP.POP.TOTL, BX.GSR.CMCP.ZS, BM.GSR.NFSV.CD) | no | ~1 year |

---

## Reproducibility

```bash
python cldv/setup_cldv.py            # create DB + schema
python cldv/run_cldv.py --only si3   # World Bank services-trade
python cldv/run_cldv.py --only si2   # ILOSTAT labor market
python cldv/run_cldv.py --only si1   # transcript collection + NLP + aggregation
python cldv/run_cldv.py --only scoring
```
All raw values, sources, and scores persist in the `cldv` Postgres database.
