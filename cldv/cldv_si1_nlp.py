"""SI1 NLP scorer — two-track deterministic displacement scoring.

Real earnings calls (esp. banks) express labor displacement as "efficiency" /
"headcount reduction" without naming AI. So we compute TWO scores per transcript:

  • proxy_score  (PRIMARY)  — broad efficiency/headcount-reduction language,
    amplified when AI/automation terms co-occur in the call.
  • strict_score (CROSS-CHECK) — displacement counted ONLY when AI is explicitly
    attributed (explicit AI phrases, or a proxy phrase with an AI term nearby).

Both use the spec formula: score = (displacement_density − augmentation_density)
× investment_to_hiring_ratio, normalized to −1..+1 via tanh. The dictionary is a
versioned, validation-expanded artifact (cldv_si1_dictionary).
"""
import math
import re
from collections import defaultdict

from cldv_si1_dictionary import (CATEGORIES, AI_TERMS, DISPLACEMENT_PROXY,
                                 DISPLACEMENT, NEGATIONS, EXCLUSIONS)

NORM_SCALE = 5.0
AI_CONTEXT_K = 0.10          # proxy amplification per unit AI density (/1k words)
CO_WINDOW = 240              # chars: AI co-occurrence window for the strict track
_EPS = 1e-3
_NEG_WINDOW_CHARS = 28


def _phrase_re(phrase: str) -> re.Pattern:
    body = r"\s+".join(re.escape(tok) for tok in phrase.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


_C_AUG  = [_phrase_re(p) for p in CATEGORIES["augmentation"]]
_C_INV  = [_phrase_re(p) for p in CATEGORIES["investment"]]
_C_HIRE = [_phrase_re(p) for p in CATEGORIES["hiring"]]
_C_DISP_EXPLICIT = [_phrase_re(p) for p in DISPLACEMENT]       # AI already named
_C_DISP_PROXY    = [_phrase_re(p) for p in DISPLACEMENT_PROXY] # efficiency lang
_C_AI   = [_phrase_re(p) for p in AI_TERMS]
_EXCL   = [_phrase_re(p) for p in EXCLUSIONS]
_NEG_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in NEGATIONS) + r")\b",
                     re.IGNORECASE)


def _clean(text: str) -> str:
    for ex in _EXCL:
        text = ex.sub(" ", text)
    return text


def _negated(text: str, start: int) -> bool:
    return bool(_NEG_RE.search(text[max(0, start - _NEG_WINDOW_CHARS):start]))


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _starts(text, compiled, discount_neg=False):
    out = []
    for rx in compiled:
        for m in rx.finditer(text):
            if discount_neg and _negated(text, m.start()):
                continue
            out.append(m.start())
    return out


def _count(text, compiled, discount_neg=False):
    return len(_starts(text, compiled, discount_neg))


def score_transcript(text: str) -> dict:
    text = _clean(text or "")
    wc = max(1, word_count(text))

    ai_pos = sorted(_starts(text, _C_AI))
    aug   = _count(text, _C_AUG)
    inv   = _count(text, _C_INV)
    hire  = _count(text, _C_HIRE, discount_neg=True)

    disp_explicit = _starts(text, _C_DISP_EXPLICIT, discount_neg=True)
    disp_proxy_hits = _starts(text, _C_DISP_PROXY, discount_neg=True)

    def _near_ai(pos):
        # binary-search-ish scan; lists are small
        return any(abs(pos - a) <= CO_WINDOW for a in ai_pos)

    # PROXY track: explicit + all proxy hits
    proxy_count = len(disp_explicit) + len(disp_proxy_hits)
    # STRICT track: explicit (AI named) + proxy hits with AI co-occurrence
    strict_count = len(disp_explicit) + sum(1 for p in disp_proxy_hits if _near_ai(p))

    dens = lambda n: n / wc * 1000.0
    ai_density   = dens(len(ai_pos))
    aug_d        = dens(aug)
    inv_d        = dens(inv)
    hire_d       = dens(hire)
    inv_to_hire  = min((inv_d + _EPS) / (hire_d + _EPS), 5.0)
    ai_context   = 1.0 + AI_CONTEXT_K * ai_density

    proxy_d  = dens(proxy_count)
    strict_d = dens(strict_count)

    raw_proxy  = (proxy_d - aug_d) * inv_to_hire * ai_context
    raw_strict = (strict_d - aug_d) * inv_to_hire

    return {
        "word_count": wc,
        "ai_density": round(ai_density, 4),
        "augmentation_density": round(aug_d, 4),
        "investment_to_hiring_ratio": round(inv_to_hire, 4),
        "proxy_displacement_density": round(proxy_d, 4),
        "strict_displacement_density": round(strict_d, 4),
        "proxy_score":  round(math.tanh(raw_proxy / NORM_SCALE), 4),   # PRIMARY −1..+1
        "strict_score": round(math.tanh(raw_strict / NORM_SCALE), 4),  # cross-check
        "counts": {"displacement_explicit": len(disp_explicit),
                   "displacement_proxy": len(disp_proxy_hits),
                   "strict_displacement": strict_count,
                   "augmentation": aug, "investment": inv, "hiring": hire,
                   "ai_terms": len(ai_pos)},
    }


# ── Corpus TF-IDF weighting on the PRIMARY (proxy) signal phrases ─────────────
def _proxy_idf(docs):
    N = max(1, len(docs))
    df = defaultdict(int)
    comp = [(rx, i) for i, rx in enumerate(_C_DISP_EXPLICIT + _C_DISP_PROXY)]
    cleaned = [_clean(d or "") for d in docs]
    for rx, i in comp:
        for d in cleaned:
            if rx.search(d):
                df[i] += 1
    return {i: math.log((1 + N) / (1 + dfi)) + 1.0 for i, dfi in df.items()}


def score_corpus(docs: list) -> list:
    """Per-doc proxy score with TF-IDF-weighted displacement phrases (rarer
    signal phrases weigh more). Returns the same dict shape as score_transcript
    with an added 'tfidf' flag on proxy_score."""
    idf = _proxy_idf(docs)
    phrases = _C_DISP_EXPLICIT + _C_DISP_PROXY
    out = []
    for d in docs:
        base = score_transcript(d)
        text = _clean(d or "")
        wc = base["word_count"]
        weighted = 0.0
        for i, rx in enumerate(phrases):
            hits = sum(1 for m in rx.finditer(text) if not _negated(text, m.start()))
            weighted += hits * idf.get(i, 1.0)
        proxy_d_tfidf = weighted / wc * 1000.0
        ai_context = 1.0 + AI_CONTEXT_K * base["ai_density"]
        raw = (proxy_d_tfidf - base["augmentation_density"]) \
            * base["investment_to_hiring_ratio"] * ai_context
        base["proxy_score"] = round(math.tanh(raw / NORM_SCALE), 4)
        base["tfidf"] = True
        out.append(base)
    return out
