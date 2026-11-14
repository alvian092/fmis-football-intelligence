from pathlib import Path
import pandas as pd

from scripts.normalize_football_data import convert

def test_normalizes_football_data_csv_and_filters_dates(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "E0_2122.csv"
    source.write_text(
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
        "E0,14/08/21,Brentford,Arsenal,2,0\n"
        "E0,01/08/20,Old,Team,1,0\n"
        "E0,15/08/21,Same,Same,1,1\n"
        "E0,16/08/21,Pending,Team,,\n",
        encoding="utf-8",
    )
    output = tmp_path / "processed" / "matches.csv"
    result = convert(raw, output, "2021-07-01", "2026-06-30")
    assert len(result) == 1
    assert result.iloc[0]["date"] == "2021-08-14"
    assert result.iloc[0]["competition"] == "England Premier League"
    saved = pd.read_csv(output)
    assert list(saved.columns) == ["date", "home_team", "away_team", "home_goals", "away_goals", "competition"]
