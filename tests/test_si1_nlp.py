from cldv_si1_nlp import score_transcript, score_corpus

DISP = ("We achieved AI-driven efficiency and workforce optimization, reducing "
        "headcount through AI. We are deploying AI agents and increasing AI "
        "investment across the firm. ") * 3

AUG = ("We are upskilling and reskilling our workforce. AI as copilot augments "
       "our employees. We are expanding our team and growing headcount with "
       "strong talent acquisition. ") * 3


def test_displacement_text_scores_positive():
    s = score_transcript(DISP)
    assert s["displacement_score"] > 0.2, s
    assert s["counts"]["displacement"] >= 3


def test_augmentation_hiring_text_scores_negative():
    s = score_transcript(AUG)
    assert s["displacement_score"] < 0, s
    assert s["counts"]["augmentation"] >= 3


def test_negation_discounts_displacement():
    pos = score_transcript("workforce optimization. workforce optimization.")
    neg = score_transcript("we are not pursuing workforce optimization. "
                           "no workforce optimization.")
    assert neg["counts"]["displacement"] < pos["counts"]["displacement"]


def test_score_is_bounded():
    for txt in (DISP, AUG, "", "neutral revenue grew margins stable"):
        s = score_transcript(txt)
        assert -1.0 <= s["displacement_score"] <= 1.0


def test_corpus_tfidf_orders_displacement_above_augmentation():
    out = score_corpus([DISP, AUG, "neutral quarter, revenue grew, margins stable"])
    assert len(out) == 3
    assert out[0]["displacement_score"] > out[1]["displacement_score"]
