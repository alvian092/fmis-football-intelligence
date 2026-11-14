import pandas as pd

from scripts.backtest import run_backtest

def test_walk_forward_backtest_uses_only_prior_matches(tmp_path):
    rows = [
        ("2025-01-01", "A", "C", 1, 0),
        ("2025-01-02", "C", "B", 0, 1),
        ("2025-01-03", "A", "B", 2, 1),
        ("2025-01-04", "B", "C", 1, 0),
        ("2025-01-05", "C", "A", 1, 1),
        ("2025-01-06", "A", "B", 2, 0),
        ("2025-01-07", "B", "A", 0, 1),
    ]
    path = tmp_path / "matches.csv"
    pd.DataFrame(rows, columns=["date", "home_team", "away_team", "home_goals", "away_goals"]).to_csv(path, index=False)
    report = run_backtest(path, min_matches=4)
    assert report["matches_evaluated"] == 1
    assert report["date_from"] == "2025-01-07"
    assert 0 <= report["metrics"]["accuracy"] <= 1
    assert report["metrics"]["brier_score_multiclass_sum"] >= 0
    assert report["metrics"]["log_loss"] >= 0
