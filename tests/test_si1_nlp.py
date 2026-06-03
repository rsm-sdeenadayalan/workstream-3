from cldv_si1_nlp import score_transcript, score_corpus

DISP_AI = ("We achieved AI-driven efficiency and workforce optimization, reducing "
           "headcount through AI. We are deploying AI agents and increasing AI "
           "investment across the firm. ") * 3

AUG = ("We are upskilling and reskilling our workforce. AI as copilot augments "
       "our employees. We are expanding our team and growing headcount with "
       "strong talent acquisition. ") * 3

# Bank-style: efficiency / headcount language but NO AI attribution.
EFFICIENCY_NO_AI = ("We drove significant efficiency and cost reduction this "
                    "quarter, reducing headcount and streamlining operations "
                    "with strong expense discipline. ") * 3


def test_explicit_ai_displacement_positive_on_both_tracks():
    s = score_transcript(DISP_AI)
    assert s["proxy_score"] > 0.2, s
    assert s["strict_score"] > 0.2, s


def test_efficiency_without_ai_proxy_positive_strict_zero():
    s = score_transcript(EFFICIENCY_NO_AI)
    assert s["proxy_score"] > 0.1, s          # efficiency language IS displacement
    assert abs(s["strict_score"]) < 0.05, s   # but no AI attribution → strict ~0


def test_augmentation_hiring_negative_proxy():
    s = score_transcript(AUG)
    assert s["proxy_score"] < 0, s


def test_negation_discounts_hiring():
    pos = score_transcript("we are expanding our team. growing headcount.")
    neg = score_transcript("we are not expanding our team. no growing headcount.")
    assert neg["counts"]["hiring"] < pos["counts"]["hiring"]


def test_scores_bounded():
    for txt in (DISP_AI, AUG, EFFICIENCY_NO_AI, "", "revenue grew margins stable"):
        s = score_transcript(txt)
        assert -1.0 <= s["proxy_score"] <= 1.0
        assert -1.0 <= s["strict_score"] <= 1.0


def test_corpus_tfidf_orders_displacement_above_augmentation():
    out = score_corpus([DISP_AI, AUG, "neutral quarter, revenue grew, margins stable"])
    assert len(out) == 3
    assert out[0]["proxy_score"] > out[1]["proxy_score"]
