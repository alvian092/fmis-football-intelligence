"""Transparent football probability models with explicit settlement outcomes."""
from __future__ import annotations
from math import exp, factorial
from typing import Any
import numpy as np

def poisson_pmf(k: int, lam: float) -> float:
    if k < 0 or lam < 0:
        raise ValueError("k and lambda must be non-negative")
    return exp(-lam) * lam**k / factorial(k)

def estimate_lambdas(matches: list[dict[str, Any]], home: str, away: str) -> tuple[float, float, str]:
    """Estimate goal means from matches strictly before the requested date."""
    if not home.strip() or not away.strip() or home.strip().casefold() == away.strip().casefold():
        raise ValueError("Home and away teams must be different non-empty names")
    home_rows = [m for m in matches if m["home_team"] == home or m["away_team"] == home]
    away_rows = [m for m in matches if m["home_team"] == away or m["away_team"] == away]
    if len(home_rows) < 3 or len(away_rows) < 3:
        raise ValueError("At least 3 prior matches per team are required")
    def scored_conceded(rows: list[dict[str, Any]], team: str):
        scored, conceded = [], []
        for m in rows:
            is_home = m["home_team"] == team
            own_xg = m.get("home_xg") if is_home else m.get("away_xg")
            opp_xg = m.get("away_xg") if is_home else m.get("home_xg")
            own_goals = m["home_goals"] if is_home else m["away_goals"]
            opp_goals = m["away_goals"] if is_home else m["home_goals"]
            scored.append(float(own_xg if own_xg is not None else own_goals))
            conceded.append(float(opp_xg if opp_xg is not None else opp_goals))
        return float(np.mean(scored)), float(np.mean(conceded))
    h_for, h_against = scored_conceded(home_rows, home)
    a_for, a_against = scored_conceded(away_rows, away)
    lam_h = max(0.15, min(4.0, 0.55 * h_for + 0.45 * a_against + 0.12))
    lam_a = max(0.15, min(4.0, 0.55 * a_for + 0.45 * h_against))
    used_xg = any(m.get("home_xg") is not None or m.get("away_xg") is not None for m in home_rows + away_rows)
    return lam_h, lam_a, "mixed_xg_and_goals" if used_xg else "goals_only"

def score_matrix(lam_home: float, lam_away: float, max_goals: int = 10, rho: float = 0.0) -> np.ndarray:
    """Independent Poisson score matrix with optional Dixon-Coles correction."""
    if not (0 < lam_home <= 8 and 0 < lam_away <= 8) or max_goals < 3:
        raise ValueError("Lambda values must be in (0, 8] and max_goals at least 3")
    p_home = np.array([poisson_pmf(i, lam_home) for i in range(max_goals + 1)])
    p_away = np.array([poisson_pmf(i, lam_away) for i in range(max_goals + 1)])
    matrix = np.outer(p_home, p_away)
    if rho:
        corrections = {
            (0, 0): 1 - lam_home * lam_away * rho,
            (0, 1): 1 + lam_home * rho,
            (1, 0): 1 + lam_away * rho,
            (1, 1): 1 - rho,
        }
        for (h, a), factor in corrections.items():
            matrix[h, a] *= max(0.0, factor)
    total = float(matrix.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("Could not normalize score probabilities")
    return matrix / total

_SETTLEMENT_KEYS = ("win_full", "win_half", "push", "lose_half", "lose_full")

def _settle(value: float) -> str:
    if value > 1e-9:
        return "win_full"
    if value < -1e-9:
        return "lose_full"
    return "push"

def _line_settlement(distribution: list[tuple[int, float]], line: float, over: bool = True) -> dict[str, float]:
    """Settle O/U line; quarter lines split stake across adjacent 0.5 lines."""
    if abs(line * 4 - round(line * 4)) > 1e-8:
        raise ValueError("Totals and handicap lines must use quarter-goal increments")
    parts = [line - 0.25, line + 0.25] if round(line * 4) % 2 else [line]
    result = {k: 0.0 for k in _SETTLEMENT_KEYS}
    for goals, probability in distribution:
        outcomes = [_settle((goals - part) if over else (part - goals)) for part in parts]
        if len(outcomes) == 1:
            result[outcomes[0]] += probability
        elif outcomes[0] == outcomes[1]:
            result[outcomes[0]] += probability
        elif "push" in outcomes:
            result["win_half" if "win_full" in outcomes else "lose_half"] += probability
        else:
            raise ValueError("Unexpected quarter-line settlement state")
    return result

def _handicap_settlement(matrix: np.ndarray, line: float) -> dict[str, float]:
    if abs(line * 4 - round(line * 4)) > 1e-8:
        raise ValueError("Handicap must use quarter-goal increments")
    parts = [line - 0.25, line + 0.25] if round(line * 4) % 2 else [line]
    result = {k: 0.0 for k in _SETTLEMENT_KEYS}
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            outcomes = [_settle((h - a) + part) for part in parts]
            probability = float(matrix[h, a])
            if len(outcomes) == 1:
                result[outcomes[0]] += probability
            elif outcomes[0] == outcomes[1]:
                result[outcomes[0]] += probability
            elif "push" in outcomes:
                result["win_half" if "win_full" in outcomes else "lose_half"] += probability
            else:
                raise ValueError("Unexpected quarter-handicap settlement state")
    return result

def market_probabilities(matrix: np.ndarray, total_line: float = 2.5, handicap_home: float = -0.5) -> dict[str, Any]:
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or np.any(matrix < 0) or not np.isclose(matrix.sum(), 1.0):
        raise ValueError("Score matrix must be square, non-negative and sum to one")
    home = draw = away = 0.0
    total_dist: list[tuple[int, float]] = []
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            p = float(matrix[h, a])
            if h > a: home += p
            elif h == a: draw += p
            else: away += p
            total_dist.append((h + a, p))
    return {
        "1x2": {"home": home, "draw": draw, "away": away},
        "totals": {
            "line": total_line,
            "over": _line_settlement(total_dist, total_line, over=True),
            "under": _line_settlement(total_dist, total_line, over=False),
        },
        "asian_handicap_home": {"line": handicap_home, **_handicap_settlement(matrix, handicap_home)},
    }

def predict(lam_home: float, lam_away: float, total_line: float = 2.5, handicap_home: float = -0.5) -> dict[str, Any]:
    matrix = score_matrix(lam_home, lam_away, rho=-0.08)
    probs = market_probabilities(matrix, total_line, handicap_home)
    flat = sorted(
        ((float(matrix[h, a]), h, a) for h in range(matrix.shape[0]) for a in range(matrix.shape[1])),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    return {
        "expected_goals": {"home": lam_home, "away": lam_away},
        "most_likely_scores": [{"score": f"{h}-{a}", "probability": p} for p, h, a in flat[:5]],
        "markets": probs,
        "model": "poisson_dixon_coles",
    }
