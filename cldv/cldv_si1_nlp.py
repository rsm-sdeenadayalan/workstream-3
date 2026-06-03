"""SI1 NLP scorer — deterministic keyword/TF-IDF displacement scoring.

Per the CLDV spec, per transcript:
  (a) displacement keyword density (per 1,000 words)
  (b) augmentation keyword density
  (c) investment-to-hiring ratio
  displacement_score = (displacement_density − augmentation_density)
                       × investment_to_hiring_ratio,  normalized to −1..+1.

`score_transcript` is the per-document core (raw densities). `score_corpus`
applies TF-IDF weighting across all transcripts (rarer signal phrases weigh
more), which is what the pipeline uses; both share the same matching logic.
"""
import math
import re
from collections import defaultdict

from cldv_si1_dictionary import CATEGORIES, NEGATIONS, EXCLUSIONS

# Normalization constant for squashing the raw score into −1..+1 (calibrated
# during the validation pass; tanh keeps it bounded and monotonic).
NORM_SCALE = 5.0
_EPS = 1e-3                      # ratio smoothing
_NEG_WINDOW_CHARS = 28          # look-back window for a negation cue


def _phrase_re(phrase: str) -> re.Pattern:
    # word-boundary match; collapse internal spaces to \s+
    body = r"\s+".join(re.escape(tok) for tok in phrase.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


_COMPILED = {cat: [(_phrase_re(p), p) for p in phrases]
             for cat, phrases in CATEGORIES.items()}
_EXCLUSION_RES = [_phrase_re(p) for p in EXCLUSIONS]
_NEG_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in NEGATIONS) + r")\b",
                     re.IGNORECASE)


def _clean(text: str) -> str:
    for ex in _EXCLUSION_RES:
        text = ex.sub(" ", text)
    return text


def _negated(text: str, start: int) -> bool:
    """True if a negation cue appears just before position `start`."""
    window = text[max(0, start - _NEG_WINDOW_CHARS):start]
    return bool(_NEG_RE.search(window))


def count_category(text: str, category: str, discount_negation: bool = True) -> int:
    """Count phrase hits for a category, discounting negated hits for the
    'active claim' categories (displacement, hiring)."""
    n = 0
    apply_neg = discount_negation and category in ("displacement", "hiring")
    for rx, _phrase in _COMPILED[category]:
        for m in rx.finditer(text):
            if apply_neg and _negated(text, m.start()):
                continue
            n += 1
    return n


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def score_transcript(text: str) -> dict:
    """Per-transcript raw densities + displacement score (−1..+1)."""
    text = _clean(text or "")
    wc = max(1, word_count(text))
    counts = {cat: count_category(text, cat) for cat in CATEGORIES}
    dens = {cat: counts[cat] / wc * 1000.0 for cat in CATEGORIES}

    inv_to_hire = (dens["investment"] + _EPS) / (dens["hiring"] + _EPS)
    inv_to_hire = min(inv_to_hire, 5.0)     # cap to avoid blow-ups
    raw = (dens["displacement"] - dens["augmentation"]) * inv_to_hire
    score = math.tanh(raw / NORM_SCALE)

    return {
        "word_count": wc,
        "counts": counts,
        "displacement_density": round(dens["displacement"], 4),
        "augmentation_density": round(dens["augmentation"], 4),
        "investment_density":   round(dens["investment"], 4),
        "hiring_density":       round(dens["hiring"], 4),
        "investment_to_hiring_ratio": round(inv_to_hire, 4),
        "raw_score": round(raw, 4),
        "displacement_score": round(score, 4),   # −1..+1
    }


# ── Corpus-level TF-IDF weighting (spec: "TF-IDF weighting") ──────────────────
def tfidf_phrase_idf(docs: list) -> dict:
    """Inverse-document-frequency per phrase across the corpus."""
    N = max(1, len(docs))
    df = defaultdict(int)
    cleaned = [_clean(d or "") for d in docs]
    for cat, comp in _COMPILED.items():
        for rx, phrase in comp:
            for d in cleaned:
                if rx.search(d):
                    df[phrase] += 1
    return {phrase: math.log((1 + N) / (1 + dfi)) + 1.0 for phrase, dfi in df.items()}


def score_corpus(docs: list) -> list:
    """Score every transcript with TF-IDF-weighted phrase densities. Rarer
    signal phrases contribute more. Returns one score dict per input doc."""
    idf = tfidf_phrase_idf(docs)
    out = []
    for d in docs:
        text = _clean(d or "")
        wc = max(1, word_count(text))
        wdens = {}
        for cat, comp in _COMPILED.items():
            apply_neg = cat in ("displacement", "hiring")
            weighted = 0.0
            for rx, phrase in comp:
                hits = 0
                for m in rx.finditer(text):
                    if apply_neg and _negated(text, m.start()):
                        continue
                    hits += 1
                weighted += hits * idf.get(phrase, 1.0)
            wdens[cat] = weighted / wc * 1000.0
        inv_to_hire = min((wdens["investment"] + _EPS) / (wdens["hiring"] + _EPS), 5.0)
        raw = (wdens["displacement"] - wdens["augmentation"]) * inv_to_hire
        out.append({
            "displacement_density": round(wdens["displacement"], 4),
            "augmentation_density": round(wdens["augmentation"], 4),
            "investment_to_hiring_ratio": round(inv_to_hire, 4),
            "raw_score": round(raw, 4),
            "displacement_score": round(math.tanh(raw / NORM_SCALE), 4),
            "tfidf_weighted": True,
        })
    return out
