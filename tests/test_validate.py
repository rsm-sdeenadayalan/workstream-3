from cldv_si1_validate import label, _concordance


def test_label_bands():
    assert label(0.5) == "displacement"
    assert label(-0.5) == "augmentation"
    assert label(0.0) == "neutral"
    assert label(0.05) == "neutral"      # within the neutral band
    assert label(None) == ""


def test_concordance_full_agreement():
    pairs = [("displacement", "displacement"), ("neutral", "neutral")]
    rate, n = _concordance(pairs)
    assert rate == 1.0 and n == 2


def test_concordance_half():
    pairs = [("displacement", "displacement"), ("neutral", "augmentation")]
    rate, n = _concordance(pairs)
    assert rate == 0.5 and n == 2


def test_concordance_empty():
    assert _concordance([]) == (0.0, 0)
