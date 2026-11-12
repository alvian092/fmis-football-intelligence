import pytest
from backend.app.models import poisson_pmf, score_matrix, market_probabilities, predict

def test_poisson_distribution_is_valid():
    assert poisson_pmf(0, 1.0) == pytest.approx(0.367879, rel=1e-4)
    with pytest.raises(ValueError):
        poisson_pmf(-1, 1.0)

def test_score_matrix_normalizes_and_is_nonnegative():
    m = score_matrix(1.4, 1.1, rho=-0.08)
    assert m.sum() == pytest.approx(1.0)
    assert (m >= 0).all()

def test_1x2_and_full_half_totals_settlements():
    p = predict(1.5, 1.0)["markets"]
    assert sum(p["1x2"].values()) == pytest.approx(1.0)
    for side in ("over", "under"):
        assert sum(p["totals"][side].values()) == pytest.approx(1.0)

def test_quarter_handicap_settlement_sums_to_one():
    p = market_probabilities(score_matrix(1.4, 1.0), 2.5, -0.25)["asian_handicap_home"]
    assert sum(p[k] for k in ["win_full", "win_half", "push", "lose_half", "lose_full"]) == pytest.approx(1.0)

def test_quarter_totals_settlement_sums_to_one_and_pushes_half():
    m = score_matrix(1.4, 1.0)
    p = market_probabilities(m, 2.25, -0.25)["totals"]
    for side in ("over", "under"):
        assert sum(p[side].values()) == pytest.approx(1.0)
    assert p["over"]["lose_half"] > 0
    assert p["under"]["win_half"] > 0

def test_invalid_market_line_rejected():
    with pytest.raises(ValueError):
        market_probabilities(score_matrix(1.2, 1.0), 2.1, -0.5)

def test_invalid_lambdas_rejected():
    with pytest.raises(ValueError):
        score_matrix(0, 1.0)
