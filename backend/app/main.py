from __future__ import annotations
from datetime import date
from io import StringIO
import os
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from .models import estimate_lambdas, predict
from .analyst import explain

app = FastAPI(title="FMIS API", version="0.1.1", description="CSV-first football probability research API")
origins = [x.strip() for x in os.getenv("FMIS_CORS_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Admin-Token"])
REQUIRED = {"date", "home_team", "away_team", "home_goals", "away_goals"}
DATA: list[dict] = []

class AnalyzeRequest(BaseModel):
    home_team: str = Field(min_length=1, max_length=100)
    away_team: str = Field(min_length=1, max_length=100)
    as_of: date
    total_line: float = Field(default=2.5, ge=0.5, le=8.5)
    handicap_home: float = Field(default=-0.5, ge=-3.0, le=3.0)

    @model_validator(mode="after")
    def teams_must_differ(self):
        if self.home_team.strip().casefold() == self.away_team.strip().casefold():
            raise ValueError("Home and away teams must be different")
        for name, value in (("total_line", self.total_line), ("handicap_home", self.handicap_home)):
            if abs(value * 4 - round(value * 4)) > 1e-8:
                raise ValueError(f"{name} must use quarter-goal increments")
        return self

@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version, "matches_loaded": len(DATA)}

@app.post("/api/data/csv")
async def upload_csv(file: UploadFile = File(...), x_admin_token: str | None = Header(default=None)):
    global DATA
    admin_token = os.getenv("FMIS_ADMIN_TOKEN")
    if not admin_token:
        raise HTTPException(503, "CSV upload is disabled until FMIS_ADMIN_TOKEN is configured")
    if x_admin_token != admin_token:
        raise HTTPException(403, "Invalid admin token")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")
    raw = await file.read()
    if len(raw) > 10_000_000:
        raise HTTPException(413, "CSV exceeds 10 MB")
    try:
        df = pd.read_csv(StringIO(raw.decode("utf-8-sig")))
        missing = REQUIRED - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        if df.empty:
            raise ValueError("CSV contains no match rows")
        df["date"] = pd.to_datetime(df["date"], errors="raise").dt.date
        for col in ("home_goals", "away_goals"):
            df[col] = pd.to_numeric(df[col], errors="raise")
            if df[col].isna().any() or (df[col] < 0).any() or (df[col] % 1 != 0).any():
                raise ValueError(f"{col} must contain non-negative whole numbers")
        for col in ("home_xg", "away_xg"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if (df[col].dropna() < 0).any():
                    raise ValueError(f"{col} cannot be negative")
        if df[["home_team", "away_team"]].isna().any().any():
            raise ValueError("Team names cannot be blank")
        df["home_team"] = df["home_team"].astype(str).str.strip()
        df["away_team"] = df["away_team"].astype(str).str.strip()
        if (df["home_team"] == "").any() or (df["away_team"] == "").any():
            raise ValueError("Team names cannot be blank")
        if (df["home_team"].str.casefold() == df["away_team"].str.casefold()).any():
            raise ValueError("A team cannot play against itself")
        df = df.astype(object).where(pd.notna(df), None)
        DATA = df.to_dict(orient="records")
        return {"loaded": len(DATA), "columns": list(df.columns), "status": "validated"}
    except Exception as exc:
        raise HTTPException(400, f"Invalid CSV: {exc}") from exc

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not DATA:
        raise HTTPException(409, "Upload historical CSV data first")
    prior = [m for m in DATA if m["date"] < req.as_of]
    try:
        lh, la, quality = estimate_lambdas(prior, req.home_team, req.away_team)
        result = predict(lh, la, req.total_line, req.handicap_home)
        result["analyst"] = explain(req.home_team, req.away_team, result, quality)
        result["data_quality"] = {"basis": quality, "prior_matches": len(prior), "as_of": req.as_of.isoformat()}
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.get("/")
def root():
    return {"name": "FMIS", "version": app.version, "docs": "/docs", "health": "/api/health"}
