#!/usr/bin/env python3
"""Chronological, no-future-leakage backtest for FMIS 1X2 probabilities."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from backend.app.models import predict

def run_backtest(csv_path: Path, min_matches: int = 3, bins_count: int = 10) -> dict:
    df = pd.read_csv(csv_path)
    required = {"date", "home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["home_goals"] = pd.to_numeric(df["home_goals"], errors="coerce")
    df["away_goals"] = pd.to_numeric(df["away_goals"], errors="coerce")
    df = df.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"]).copy()
    df = df[(df.home_goals >= 0) & (df.away_goals >= 0)]
    df = df.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("No valid completed matches found")

    stats = defaultdict(lambda: {"played": 0, "for_sum": 0.0, "against_sum": 0.0})
    evaluated = []
    skipped = 0

    # All matches on a calendar date are predicted from the state before that
    # date; results are added only after every fixture on the date is evaluated.
    for match_date, day in df.groupby("date", sort=True):
        day_updates = []
        for row in day.itertuples(index=False):
            home, away = str(row.home_team).strip(), str(row.away_team).strip()
            if not home or not away or home.casefold() == away.casefold():
                skipped += 1
                continue
            hs, aws = stats[home], stats[away]
            if hs["played"] < min_matches or aws["played"] < min_matches:
                skipped += 1
            else:
                h_for = hs["for_sum"] / hs["played"]
                h_against = hs["against_sum"] / hs["played"]
                a_for = aws["for_sum"] / aws["played"]
                a_against = aws["against_sum"] / aws["played"]
                lam_home = max(0.15, min(4.0, 0.55 * h_for + 0.45 * a_against + 0.12))
                lam_away = max(0.15, min(4.0, 0.55 * a_for + 0.45 * h_against))
                probabilities = predict(lam_home, lam_away)["markets"]["1x2"]
                actual = "home" if row.home_goals > row.away_goals else "away" if row.home_goals < row.away_goals else "draw"
                evaluated.append({
                    "date": match_date.strftime("%Y-%m-%d"),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": int(row.home_goals),
                    "away_goals": int(row.away_goals),
                    "actual": actual,
                    "p_home": probabilities["home"],
                    "p_draw": probabilities["draw"],
                    "p_away": probabilities["away"],
                })
            day_updates.append((home, away, int(row.home_goals), int(row.away_goals)))

        for home, away, hg, ag in day_updates:
            stats[home]["played"] += 1
            stats[home]["for_sum"] += hg
            stats[home]["against_sum"] += ag
            stats[away]["played"] += 1
            stats[away]["for_sum"] += ag
            stats[away]["against_sum"] += hg

    if not evaluated:
        raise ValueError("No fixtures had enough prior history; add more seasons or lower --min-matches")

    correct = 0
    brier_total = 0.0
    log_loss_total = 0.0
    bins = [{"count": 0, "confidence_sum": 0.0, "accuracy_sum": 0.0} for _ in range(bins_count)]
    for item in evaluated:
        probs = {"home": item["p_home"], "draw": item["p_draw"], "away": item["p_away"]}
        predicted = max(probs, key=probs.get)
        hit = predicted == item["actual"]
        correct += int(hit)
        brier_total += sum((probs[k] - (1.0 if k == item["actual"] else 0.0)) ** 2 for k in probs)
        log_loss_total += -__import__("math").log(max(1e-15, probs[item["actual"]]))
        confidence = probs[predicted]
        bucket = min(bins_count - 1, int(confidence * bins_count))
        bins[bucket]["count"] += 1
        bins[bucket]["confidence_sum"] += confidence
        bins[bucket]["accuracy_sum"] += int(hit)

    n = len(evaluated)
    calibration = [
        {
            "range": f"{i / bins_count:.1f}-{(i + 1) / bins_count:.1f}",
            "count": b["count"],
            "mean_confidence": b["confidence_sum"] / b["count"],
            "observed_accuracy": b["accuracy_sum"] / b["count"],
        }
        for i, b in enumerate(bins) if b["count"]
    ]
    return {
        "model": "poisson_dixon_coles",
        "method": "chronological_walk_forward_no_same_day_leakage",
        "matches_evaluated": n,
        "matches_skipped_for_history_or_validation": skipped,
        "date_from": evaluated[0]["date"],
        "date_to": evaluated[-1]["date"],
        "metrics": {
            "accuracy": correct / n,
            "brier_score_multiclass_sum": brier_total / n,
            "log_loss": log_loss_total / n,
        },
        "calibration": calibration,
        "predictions": evaluated,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/fmis_matches.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/backtest_report.json"))
    parser.add_argument("--min-matches", type=int, default=3)
    args = parser.parse_args()
    report = run_backtest(args.input, min_matches=args.min_matches)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "predictions"}, indent=2))
    print(f"Full per-match predictions saved to {args.output}")

if __name__ == "__main__":
    main()
