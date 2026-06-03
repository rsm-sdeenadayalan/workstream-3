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

DICTIONARY_VERSION = "0.1.0"

DISPLACEMENT = [
    "ai-driven efficiency", "ai driven efficiency",
    "reduced headcount through ai", "headcount reduction",
    "workforce optimization", "workforce optimisation",
    "reduce headcount", "reducing headcount", "lower headcount",
    "efficiency through automation", "automation efficiency",
    "do more with less", "operating leverage from ai",
    "ai-enabled productivity", "fewer employees", "right-sizing",
    "restructuring", "labor cost reduction", "labour cost reduction",
    "replace manual", "eliminate manual", "reduce manual effort",
    "automating tasks", "automate routine", "displacing",
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
