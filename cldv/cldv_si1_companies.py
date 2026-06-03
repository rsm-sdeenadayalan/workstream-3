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
    {"company": "JPMorgan Chase", "country_iso": "US", "sector": FIN,  "us_ticker": "JPM",   "exchange": "NYSE",   "ir_domain": "jpmorganchase.com"},
    {"company": "Goldman Sachs",  "country_iso": "US", "sector": FIN,  "us_ticker": "GS",    "exchange": "NYSE",   "ir_domain": "goldmansachs.com"},
    {"company": "Citigroup",      "country_iso": "US", "sector": FIN,  "us_ticker": "C",     "exchange": "NYSE",   "ir_domain": "citigroup.com"},
    {"company": "Microsoft",      "country_iso": "US", "sector": TECH, "us_ticker": "MSFT",  "exchange": "NASDAQ", "ir_domain": "microsoft.com"},
    {"company": "Alphabet",       "country_iso": "US", "sector": TECH, "us_ticker": "GOOGL", "exchange": "NASDAQ", "ir_domain": "abc.xyz"},
    {"company": "Amazon",         "country_iso": "US", "sector": TECH, "us_ticker": "AMZN",  "exchange": "NASDAQ", "ir_domain": "aboutamazon.com"},
    {"company": "Meta Platforms", "country_iso": "US", "sector": TECH, "us_ticker": "META",  "exchange": "NASDAQ", "ir_domain": "investor.atmeta.com"},
    {"company": "Salesforce",     "country_iso": "US", "sector": TECH, "us_ticker": "CRM",   "exchange": "NYSE",   "ir_domain": "salesforce.com"},
    {"company": "Accenture",      "country_iso": "US", "sector": ITS,  "us_ticker": "ACN",   "exchange": "NYSE",   "ir_domain": "accenture.com"},
    {"company": "IBM",            "country_iso": "US", "sector": TECH, "us_ticker": "IBM",   "exchange": "NYSE",   "ir_domain": "ibm.com"},

    # ── India ────────────────────────────────────────────────────────────────
    {"company": "Infosys",        "country_iso": "IN", "sector": ITS, "us_ticker": "INFY", "exchange": "NSE/NYSE", "ir_domain": "infosys.com"},
    {"company": "Wipro",          "country_iso": "IN", "sector": ITS, "us_ticker": "WIT",  "exchange": "NSE/NYSE", "ir_domain": "wipro.com"},
    {"company": "Tata Consultancy Services", "country_iso": "IN", "sector": ITS, "us_ticker": None, "exchange": "NSE", "ir_domain": "tcs.com"},
    {"company": "HCLTech",        "country_iso": "IN", "sector": ITS, "us_ticker": None, "exchange": "NSE", "ir_domain": "hcltech.com"},
    {"company": "Tech Mahindra",  "country_iso": "IN", "sector": ITS, "us_ticker": None, "exchange": "NSE", "ir_domain": "techmahindra.com"},
    {"company": "Cognizant",      "country_iso": "IN", "sector": ITS, "us_ticker": "CTSH", "exchange": "NASDAQ", "ir_domain": "cognizant.com"},
    {"company": "Genpact",        "country_iso": "IN", "sector": BPO, "us_ticker": "G",    "exchange": "NYSE",   "ir_domain": "genpact.com"},
    {"company": "WNS Holdings",   "country_iso": "IN", "sector": BPO, "us_ticker": "WNS",  "exchange": "NYSE",   "ir_domain": "wns.com"},
    {"company": "EXL Service",    "country_iso": "IN", "sector": BPO, "us_ticker": "EXLS", "exchange": "NASDAQ", "ir_domain": "exlservice.com"},

    # ── Singapore ────────────────────────────────────────────────────────────
    {"company": "DBS Group",      "country_iso": "SG", "sector": FIN,  "us_ticker": None, "exchange": "SGX", "ir_domain": "dbs.com"},
    {"company": "OCBC",           "country_iso": "SG", "sector": FIN,  "us_ticker": None, "exchange": "SGX", "ir_domain": "ocbc.com"},
    {"company": "UOB",            "country_iso": "SG", "sector": FIN,  "us_ticker": None, "exchange": "SGX", "ir_domain": "uobgroup.com"},
    {"company": "Grab Holdings",  "country_iso": "SG", "sector": PLAT, "us_ticker": "GRAB", "exchange": "NASDAQ", "ir_domain": "grab.com"},
    {"company": "Sea Limited",    "country_iso": "SG", "sector": PLAT, "us_ticker": "SE",   "exchange": "NYSE",   "ir_domain": "seagroup.com"},

    # ── Philippines ──────────────────────────────────────────────────────────
    {"company": "Concentrix",     "country_iso": "PH", "sector": BPO, "us_ticker": "CNXC", "exchange": "NASDAQ", "ir_domain": "concentrix.com"},
    {"company": "TaskUs",         "country_iso": "PH", "sector": BPO, "us_ticker": "TASK", "exchange": "NASDAQ", "ir_domain": "taskus.com"},
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
    {"company": "Itaú Unibanco",  "country_iso": "BR", "sector": FIN,  "us_ticker": "ITUB", "exchange": "B3/NYSE", "ir_domain": "itau.com.br"},
    {"company": "Bradesco",       "country_iso": "BR", "sector": FIN,  "us_ticker": "BBD",  "exchange": "B3/NYSE", "ir_domain": "bradesco.com.br"},
    {"company": "Nubank",         "country_iso": "BR", "sector": PLAT, "us_ticker": "NU",   "exchange": "NYSE",    "ir_domain": "nu.com.br"},
    {"company": "TOTVS",          "country_iso": "BR", "sector": ITS,  "us_ticker": None, "exchange": "B3", "ir_domain": "totvs.com"},
    {"company": "CI&T",           "country_iso": "BR", "sector": ITS,  "us_ticker": "CINT", "exchange": "NYSE", "ir_domain": "ciandt.com"},
]


# Approximate global headcount (public figures, ~2024-25) used for the
# employment-weighted country aggregation the spec requires. Relative weights
# within a country are what matter, so approximate counts are adequate; refine
# from filings during validation. Global BPO counts (Concentrix/Teleperformance)
# are global totals — a documented approximation.
EMPLOYEES = {
    "JPMorgan Chase": 310000, "Goldman Sachs": 46000, "Citigroup": 229000,
    "Microsoft": 228000, "Alphabet": 183000, "Amazon": 1550000,
    "Meta Platforms": 67000, "Salesforce": 73000, "Accenture": 774000, "IBM": 282000,
    "Infosys": 317000, "Wipro": 234000, "Tata Consultancy Services": 607000,
    "HCLTech": 219000, "Tech Mahindra": 148000, "Cognizant": 336000,
    "Genpact": 125000, "WNS Holdings": 60000, "EXL Service": 55000,
    "DBS Group": 36000, "OCBC": 30000, "UOB": 26000, "Grab Holdings": 11000,
    "Sea Limited": 67000,
    "Concentrix": 440000, "TaskUs": 60000, "Teleperformance": 490000,
    "Emirates NBD": 28000, "First Abu Dhabi Bank": 10000, "e& (Etisalat)": 50000,
    "Itaú Unibanco": 100000, "Bradesco": 85000, "Nubank": 8000,
    "TOTVS": 14000, "CI&T": 7000,
}


def active_companies():
    """Companies we will actually collect (excludes 'drop')."""
    return [c for c in COMPANIES if c.get("status") != "drop"]


def employees_for(company) -> int:
    name = company["company"] if isinstance(company, dict) else company
    return EMPLOYEES.get(name, 0)


def us_listed(c) -> bool:
    return bool(c.get("us_ticker"))
