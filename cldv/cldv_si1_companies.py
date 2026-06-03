"""SI1 company roster (~40 firms across the 6 countries, per the CLDV spec).

Each entry carries the metadata the transcript collector needs to choose a
source path:
  - us_ticker : if the firm files with the SEC / has US-listed transcripts, the
                Motley Fool + EDGAR path can be used directly (the easy tier).
  - exchange  : primary listing (for IR-site lookups when not US-listed).
  - ir_domain : investor-relations domain for the agent-located transcript path.
  - status    : 'active' | 'substitute' | 'drop' (with reason) — gaps are honest.

`sector` groups firms for employment-weighted country aggregation and reporting.
"""

# sector tags
FIN  = "financial_services"
TECH = "technology"
ITS  = "it_services"
BPO  = "bpo"
TEL  = "telecom"
PLAT = "fintech_platform"

COMPANIES = [
    # ── United States ────────────────────────────────────────────────────────
    {"company": "JPMorgan Chase", "country_iso": "US", "sector": FIN,  "us_ticker": "JPM",   "exchange": "NYSE"},
    {"company": "Goldman Sachs",  "country_iso": "US", "sector": FIN,  "us_ticker": "GS",    "exchange": "NYSE"},
    {"company": "Citigroup",      "country_iso": "US", "sector": FIN,  "us_ticker": "C",     "exchange": "NYSE"},
    {"company": "Microsoft",      "country_iso": "US", "sector": TECH, "us_ticker": "MSFT",  "exchange": "NASDAQ"},
    {"company": "Alphabet",       "country_iso": "US", "sector": TECH, "us_ticker": "GOOGL", "exchange": "NASDAQ"},
    {"company": "Amazon",         "country_iso": "US", "sector": TECH, "us_ticker": "AMZN",  "exchange": "NASDAQ"},
    {"company": "Meta Platforms", "country_iso": "US", "sector": TECH, "us_ticker": "META",  "exchange": "NASDAQ"},
    {"company": "Salesforce",     "country_iso": "US", "sector": TECH, "us_ticker": "CRM",   "exchange": "NYSE"},
    {"company": "Accenture",      "country_iso": "US", "sector": ITS,  "us_ticker": "ACN",   "exchange": "NYSE"},
    {"company": "IBM",            "country_iso": "US", "sector": TECH, "us_ticker": "IBM",   "exchange": "NYSE"},

    # ── India ────────────────────────────────────────────────────────────────
    {"company": "Infosys",        "country_iso": "IN", "sector": ITS, "us_ticker": "INFY", "exchange": "NSE/NYSE"},
    {"company": "Wipro",          "country_iso": "IN", "sector": ITS, "us_ticker": "WIT",  "exchange": "NSE/NYSE"},
    {"company": "Tata Consultancy Services", "country_iso": "IN", "sector": ITS, "us_ticker": None, "exchange": "NSE", "ir_domain": "tcs.com"},
    {"company": "HCLTech",        "country_iso": "IN", "sector": ITS, "us_ticker": None, "exchange": "NSE", "ir_domain": "hcltech.com"},
    {"company": "Tech Mahindra",  "country_iso": "IN", "sector": ITS, "us_ticker": None, "exchange": "NSE", "ir_domain": "techmahindra.com"},
    {"company": "Cognizant",      "country_iso": "IN", "sector": ITS, "us_ticker": "CTSH", "exchange": "NASDAQ"},
    {"company": "Genpact",        "country_iso": "IN", "sector": BPO, "us_ticker": "G",    "exchange": "NYSE"},
    {"company": "WNS Holdings",   "country_iso": "IN", "sector": BPO, "us_ticker": "WNS",  "exchange": "NYSE"},
    {"company": "EXL Service",    "country_iso": "IN", "sector": BPO, "us_ticker": "EXLS", "exchange": "NASDAQ"},

    # ── Singapore ────────────────────────────────────────────────────────────
    {"company": "DBS Group",      "country_iso": "SG", "sector": FIN,  "us_ticker": None, "exchange": "SGX", "ir_domain": "dbs.com"},
    {"company": "OCBC",           "country_iso": "SG", "sector": FIN,  "us_ticker": None, "exchange": "SGX", "ir_domain": "ocbc.com"},
    {"company": "UOB",            "country_iso": "SG", "sector": FIN,  "us_ticker": None, "exchange": "SGX", "ir_domain": "uobgroup.com"},
    {"company": "Grab Holdings",  "country_iso": "SG", "sector": PLAT, "us_ticker": "GRAB", "exchange": "NASDAQ"},
    {"company": "Sea Limited",    "country_iso": "SG", "sector": PLAT, "us_ticker": "SE",   "exchange": "NYSE"},

    # ── Philippines ──────────────────────────────────────────────────────────
    {"company": "Concentrix",     "country_iso": "PH", "sector": BPO, "us_ticker": "CNXC", "exchange": "NASDAQ"},
    {"company": "TaskUs",         "country_iso": "PH", "sector": BPO, "us_ticker": "TASK", "exchange": "NASDAQ"},
    {"company": "Teleperformance","country_iso": "PH", "sector": BPO, "us_ticker": None, "exchange": "Euronext Paris", "ir_domain": "teleperformance.com"},
    {"company": "Accenture Philippines", "country_iso": "PH", "sector": ITS, "us_ticker": None,
     "status": "drop", "reason": "not separable from global Accenture (ACN) reporting"},

    # ── United Arab Emirates ─────────────────────────────────────────────────
    {"company": "Emirates NBD",   "country_iso": "AE", "sector": FIN, "us_ticker": None, "exchange": "DFM", "ir_domain": "emiratesnbd.com"},
    {"company": "First Abu Dhabi Bank", "country_iso": "AE", "sector": FIN, "us_ticker": None, "exchange": "ADX", "ir_domain": "bankfab.com"},
    {"company": "e& (Etisalat)",  "country_iso": "AE", "sector": TEL, "us_ticker": None, "exchange": "ADX", "ir_domain": "eand.com"},
    {"company": "Mubadala portfolio", "country_iso": "AE", "sector": "sovereign_investment", "us_ticker": None,
     "status": "substitute", "reason": "diffuse holding co — substitute a listed proxy or drop; no single earnings call"},

    # ── Brazil ───────────────────────────────────────────────────────────────
    {"company": "Itaú Unibanco",  "country_iso": "BR", "sector": FIN,  "us_ticker": "ITUB", "exchange": "B3/NYSE"},
    {"company": "Bradesco",       "country_iso": "BR", "sector": FIN,  "us_ticker": "BBD",  "exchange": "B3/NYSE"},
    {"company": "Nubank",         "country_iso": "BR", "sector": PLAT, "us_ticker": "NU",   "exchange": "NYSE"},
    {"company": "TOTVS",          "country_iso": "BR", "sector": ITS,  "us_ticker": None, "exchange": "B3", "ir_domain": "totvs.com"},
    {"company": "CI&T",           "country_iso": "BR", "sector": ITS,  "us_ticker": "CINT", "exchange": "NYSE"},
]


def active_companies():
    """Companies we will actually collect (excludes 'drop')."""
    return [c for c in COMPANIES if c.get("status") != "drop"]


def us_listed(c) -> bool:
    return bool(c.get("us_ticker"))
