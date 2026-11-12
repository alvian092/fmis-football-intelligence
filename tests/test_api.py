import pytest
from fastapi.testclient import TestClient
from backend.app import main

client = TestClient(main.app)
CSV = b"date,home_team,away_team,home_goals,away_goals,home_xg,away_xg\n2025-01-01,A,B,2,1,1.8,0.9\n2025-01-02,B,A,0,1,0.4,1.1\n2025-01-03,A,C,1,0,1.0,0.3\n2025-01-04,C,A,2,2,1.2,1.5\n2025-01-05,A,B,3,1,2.2,0.8\n2025-01-06,B,C,1,0,1.0,0.5\n2025-01-07,C,B,0,2,0.6,1.7\n2025-01-08,B,A,1,2,0.9,1.8\n2025-01-09,A,C,2,0,1.6,0.4\n2025-01-10,C,B,1,1,0.9,1.0\n"

@pytest.fixture(autouse=True)
def reset_data(monkeypatch):
    main.DATA = []
    monkeypatch.setenv("FMIS_ADMIN_TOKEN", "test-token")
    yield
    main.DATA = []

def test_health():
    assert client.get("/api/health").status_code == 200

def test_upload_rejects_bad_schema_with_valid_admin_token():
    response = client.post("/api/data/csv", headers={"X-Admin-Token": "test-token"}, files={"file": ("bad.csv", b"hello\nworld", "text/csv")})
    assert response.status_code == 400

def test_upload_requires_admin_token():
    response = client.post("/api/data/csv", files={"file": ("matches.csv", CSV, "text/csv")})
    assert response.status_code == 403

def test_upload_and_analyze_happy_path():
    uploaded = client.post("/api/data/csv", headers={"X-Admin-Token": "test-token"}, files={"file": ("matches.csv", CSV, "text/csv")})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["loaded"] == 10
    result = client.post("/api/analyze", json={"home_team": "A", "away_team": "B", "as_of": "2025-02-01", "total_line": 2.25, "handicap_home": -0.25})
    assert result.status_code == 200, result.text
    body = result.json()
    assert sum(body["markets"]["1x2"].values()) == pytest.approx(1)
    assert sum(body["markets"]["totals"]["over"].values()) == pytest.approx(1)
    assert body["analyst"]["decision"] == "ANALYSIS_ONLY"

def test_analyze_requires_data():
    response = client.post("/api/analyze", json={"home_team": "A", "away_team": "B", "as_of": "2026-01-01"})
    assert response.status_code == 409

def test_upload_rejects_negative_goals():
    bad = b"date,home_team,away_team,home_goals,away_goals\n2025-01-01,A,B,-1,0\n"
    response = client.post("/api/data/csv", headers={"X-Admin-Token": "test-token"}, files={"file": ("bad.csv", bad, "text/csv")})
    assert response.status_code == 400
