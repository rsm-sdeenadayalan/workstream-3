"""SI1 keyword dictionary — four phrase categories that drive the corporate
displacement score (per the CLDV spec), plus exclusion rules.

This is a VERSIONED, VALIDATED artifact (a spec deliverable). The seed phrases
below come from the spec; the human 2-reviewer concordance pass (cldv_si1_validate)
appends missed signals and exclusion rules here, bumping DICTIONARY_VERSION.

Categories:
  displacement  — displacement-positive: AI replacing / reducing cognitive labor
  augmentation  — displacement-negative: AI augmenting / upskilling workers
  investment    — AI capex / deployment intensity
  hiring        — workforce expansion

Phrases are matched case-insensitively on word boundaries; multi-word phrases
match across normal whitespace.
"""

DICTIONARY_VERSION = "0.2.0"

# AI / automation terms — used to (a) gate the STRICT track (displacement only
# counts when AI co-occurs nearby) and (b) amplify the PROXY track in AI-heavy
# calls. Tokens are word-boundary matched, so "ai" matches standalone "AI".
AI_TERMS = [
    "artificial intelligence", "ai", "a.i.", "machine learning",
    "generative ai", "gen ai", "genai", "large language model", "llm",
    "automation", "automate", "automating", "automated", "copilot", "co-pilot",
    "algorithm", "algorithmic", "robotic process automation", "rpa",
    "digital labor", "digital labour", "intelligent automation",
]

# PROXY displacement signal — efficiency / headcount-reduction language that
# real calls (esp. banks) use WITHOUT naming AI. Counts in the proxy track;
# counts in the strict track only when an AI term co-occurs in the same window.
DISPLACEMENT_PROXY = [
    "efficiency", "efficiencies", "operating leverage", "expense discipline",
    "cost discipline", "cost reduction", "reduce costs", "reducing costs",
    "reduce headcount", "reducing headcount", "lower headcount",
    "headcount reduction", "headcount reductions", "do more with less",
    "streamline", "streamlining", "rationalize", "rationalization",
    "rationalise", "restructuring", "right-size", "right-sizing", "right size",
    "productivity gains", "productivity improvement", "fewer roles",
    "fewer employees", "leaner", "cost takeout", "cost take-out",
    "structural cost", "simplification",
    # generics that name neither AI nor automation (strict track ignores unless
    # an AI term co-occurs nearby):
    "workforce optimization", "workforce optimisation", "labor cost reduction",
    "labour cost reduction", "replace manual", "eliminate manual",
    "reduce manual effort", "displacing",
]

# EXPLICIT displacement — phrases that NAME AI/automation as the driver. These
# count on BOTH the strict and proxy tracks. Generic efficiency/headcount
# language (which does NOT name AI) lives in DISPLACEMENT_PROXY below.
DISPLACEMENT = [
    "ai-driven efficiency", "ai driven efficiency", "ai efficiency",
    "reduced headcount through ai", "reducing headcount through ai",
    "headcount reduction through ai", "ai-enabled productivity",
    "ai enabled productivity", "ai-driven productivity",
    "efficiency through automation", "automation efficiency",
    "automating tasks", "automate routine", "automating routine",
    "replaced by ai", "replaced by automation", "displaced by ai",
    "operating leverage from ai", "ai-driven cost", "automation-driven",
]

AUGMENTATION = [
    "ai-augmented workforce", "ai augmented workforce",
    "upskilling", "reskilling", "ai as copilot", "ai copilot",
    "augment our employees", "augmenting our workforce",
    "human in the loop", "empower our employees", "employee productivity tools",
    "augmentation not replacement", "ai assists", "assist our teams",
    "training our workforce", "invest in our people",
]

INVESTMENT = [
    "ai capex", "ai capital expenditure", "deploying ai agents",
    "ai budget increase", "increasing ai investment", "ai investment",
    "investing in ai", "ai infrastructure", "generative ai investment",
    "scaling ai", "ai deployment", "rolling out ai", "ai initiatives",
    "ai roadmap", "ai spend", "ramp ai",
]

HIRING = [
    "expanding team", "expanding our team", "talent acquisition",
    "growing headcount", "increasing headcount", "adding headcount",
    "hiring", "expanding workforce", "growing our workforce",
    "net hiring", "add talent", "build out our team", "ramp hiring",
    "increase staffing",
]

CATEGORIES = {
    "displacement": DISPLACEMENT,
    "augmentation": AUGMENTATION,
    "investment":   INVESTMENT,
    "hiring":       HIRING,
}

# Negation cues: a displacement/hiring hit immediately preceded (within a small
# window) by one of these is discounted (false-positive guard). Expanded during
# validation.
NEGATIONS = ["not", "no", "without", "rather than", "instead of", "avoid", "never"]

# Phrases that look like signals but are noise in these transcripts — dropped.
EXCLUSIONS = [
    "ai ethics committee",   # governance, not labor
    "headcount in line with", # neutral guidance phrasing
]
