#!/usr/bin/env python3
"""Normalize manually downloaded Football-Data.co.uk CSV files for FMIS.

The script deliberately does not scrape/download the provider. Download the
official CSV/season ZIP files yourself, extract them into data/raw, then run
this local converter. Source files are commonly Windows-1252 and use columns
such as Date, HomeTeam, AwayTeam, FTHG and FTAG.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import pandas as pd

LEAGUES = {
    "E0": "England Premier League",
    "E1": "England Championship",
    "E2": "England League One",
    "E3": "England League Two",
    "EC": "England National League",
    "SC0": "Scotland Premiership",
    "SC1": "Scotland Championship",
    "SC2": "Scotland League One",
    "SC3": "Scotland League Two",
    "D1": "Germany Bundesliga",
    "D2": "Germany 2. Bundesliga",
    "I1": "Italy Serie A",
    "I2": "Italy Serie B",
    "SP1": "Spain La Liga",
    "SP2": "Spain Segunda Division",
    "F1": "France Ligue 1",
    "F2": "France Ligue 2",
    "N1": "Netherlands Eredivisie",
    "B1": "Belgium Pro League",
    "P1": "Portugal Primeira Liga",
    "T1": "Turkey Super Lig",
    "G1": "Greece Super League",
    "ARG": "Argentina Primera Division",
    "AUT": "Austria Bundesliga",
    "BRA": "Brazil Serie A",
    "CHN": "China Super League",
    "DNK": "Denmark Superliga",
    "FIN": "Finland Veikkausliiga",
    "IRL": "Ireland Premier Division",
    "JPN": "Japan J-League",
    "MEX": "Mexico Liga MX",
    "NOR": "Norway Eliteserien",
    "POL": "Poland Ekstraklasa",
    "ROU": "Romania Liga I",
    "RUS": "Russia Premier League",
    "SWE": "Sweden Allsvenskan",
    "SWZ": "Switzerland Super League",
    "USA": "USA MLS",
}

ALIASES = {
    "date": ("date", "matchdate"),
    "home_team": ("hometeam", "home_team", "home"),
    "away_team": ("awayteam", "away_team", "away"),
    "home_goals": ("fthg", "home_goals", "hg", "homegoals"),
    "away_goals": ("ftag", "away_goals", "ag", "awaygoals"),
    "competition": ("competition", "league", "div", "division"),
}

def normalize_headers(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [
        re.sub(r"[^a-z0-9_]", "", str(c).replace("\ufeff", "").strip().lower())
        for c in frame.columns
    ]
    rename = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if alias in frame.columns:
                rename[alias] = target
                break
    return frame.rename(columns=rename)

def league_code(path: Path) -> str:
    # Handles common names such as E0.csv, E0_2122.csv and 2122_E0.csv.
    tokens = re.findall(r"[A-Za-z]{1,3}", path.stem.upper())
    for token in tokens:
        if token in LEAGUES:
            return token
    return ""

def read_source(path: Path) -> pd.DataFrame:
    last_error = None
    for encoding in ("cp1252", "utf-8-sig", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Cannot decode {path}: {last_error}")

def convert(input_dir: Path, output: Path, min_date: str, max_date: str) -> pd.DataFrame:
    files = sorted(p for p in input_dir.rglob("*.csv") if p.resolve() != output.resolve())
    if not files:
        raise ValueError(f"No CSV files found under {input_dir}")

    frames = []
    rejected_files = []
    for path in files:
        try:
            raw = normalize_headers(read_source(path))
            required = {"date", "home_team", "away_team", "home_goals", "away_goals"}
            if not required.issubset(raw.columns):
                rejected_files.append(f"{path.name}: missing {sorted(required - set(raw.columns))}")
                continue

            out = raw[["date", "home_team", "away_team", "home_goals", "away_goals"]].copy()
            out["date"] = pd.to_datetime(out["date"], dayfirst=True, errors="coerce")
            out["home_goals"] = pd.to_numeric(out["home_goals"], errors="coerce")
            out["away_goals"] = pd.to_numeric(out["away_goals"], errors="coerce")
            out["home_team"] = out["home_team"].astype("string").str.strip()
            out["away_team"] = out["away_team"].astype("string").str.strip()

            code = league_code(path)
            source_comp = raw["competition"] if "competition" in raw.columns else None
            if source_comp is not None:
                out["competition"] = source_comp.astype("string").str.strip()
                out.loc[out["competition"].isna() | (out["competition"] == ""), "competition"] = LEAGUES.get(code, code or path.stem)
            else:
                out["competition"] = LEAGUES.get(code, code or path.stem)

            valid = (
                out["date"].notna()
                & out["home_team"].notna() & out["away_team"].notna()
                & (out["home_team"] != "") & (out["away_team"] != "")
                & (out["home_team"].str.casefold() != out["away_team"].str.casefold())
                & out["home_goals"].notna() & out["away_goals"].notna()
                & (out["home_goals"] >= 0) & (out["away_goals"] >= 0)
                & (out["home_goals"] % 1 == 0) & (out["away_goals"] % 1 == 0)
            )
            out = out.loc[valid].copy()
            out = out.loc[
                (out["date"] >= pd.Timestamp(min_date))
                & (out["date"] <= pd.Timestamp(max_date))
            ]
            if not out.empty:
                out["date"] = out["date"].dt.strftime("%Y-%m-%d")
                out["home_goals"] = out["home_goals"].astype(int)
                out["away_goals"] = out["away_goals"].astype(int)
                frames.append(out)
        except Exception as exc:
            rejected_files.append(f"{path.name}: {exc}")

    if not frames:
        details = "; ".join(rejected_files[:8])
        raise ValueError("No valid match rows found. " + details)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["date", "home_team", "away_team", "competition"]
    )
    combined = combined.sort_values(["date", "competition", "home_team"]).reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False, encoding="utf-8")
    print(f"Saved {len(combined):,} matches from {combined['competition'].nunique()} competitions to {output}")
    print(combined.groupby("competition").size().sort_values(ascending=False).to_string())
    if rejected_files:
        print("\nSkipped files/notes:")
        print("\n".join(rejected_files), file=sys.stderr)
    return combined

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/fmis_matches.csv"))
    parser.add_argument("--min-date", default="2021-07-01", help="Inclusive ISO date; default covers the last five completed seasons")
    parser.add_argument("--max-date", default="2026-06-30", help="Inclusive ISO date; default ends after 2025/26")
    args = parser.parse_args()
    convert(args.input_dir, args.output, args.min_date, args.max_date)

if __name__ == "__main__":
    main()
