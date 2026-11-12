"""Explainable, deterministic Match Analyst; no external AI key required."""
def explain(home: str, away: str, prediction: dict, data_quality: str) -> dict:
    p = prediction["markets"]["1x2"]
    top = max(p, key=p.get)
    labels = {"home": home, "draw": "Draw", "away": away}
    score = prediction["most_likely_scores"][0]["score"]
    totals = prediction["markets"]["totals"]
    over = totals["over"]
    notes = [
        f"Highest modeled 1X2 outcome: {labels[top]} ({p[top]:.1%}).",
        f"Most likely exact score in the modeled score grid: {score}.",
        f"Expected goals: {prediction['expected_goals']['home']:.2f}–{prediction['expected_goals']['away']:.2f}.",
        f"Over {totals['line']} full/half-win probability: {over['win_full'] + over['win_half']:.1%}; push: {over['push']:.1%}.",
        f"Data basis: {data_quality}.",
        "These are model estimates, not guarantees; sparse history, lineups and data coverage can materially change them.",
    ]
    if max(p.values()) < 0.45:
        notes.append("No 1X2 outcome dominates the model; uncertainty is relatively high.")
    return {"headline": f"{home} vs {away}: {labels[top]} is the most likely 1X2 outcome",
            "explanations": notes, "decision": "ANALYSIS_ONLY"}
