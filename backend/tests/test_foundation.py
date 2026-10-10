import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.schemas import InquiryRequest, SearchRequest, Provider, SearchResponse


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(database_path=tmp_path / "missing.sqlite3")))


def test_default_and_environment_config(monkeypatch, tmp_path):
    monkeypatch.delenv("CARE_LEARN_DB_PATH", raising=False)
    assert Settings.from_env().database_path == Path(__file__).resolve().parents[1] / "data/caregiving.sqlite3"
    monkeypatch.setenv("CARE_LEARN_DB_PATH", str(tmp_path / "custom.sqlite3"))
    assert Settings.from_env().database_path == tmp_path / "custom.sqlite3"


def test_missing_database_does_not_create_file(client):
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "database_unavailable", "message": "Provider database is not ready."}}
    assert not client.app.state.settings.database_path.exists()
    assert "sqlite3" not in response.text


@pytest.mark.parametrize("state", ["empty", "corrupt", "wrong_version", "missing_table", "ready"])
def test_database_readiness(tmp_path, state):
    path = tmp_path / "directory.sqlite3"
    if state == "corrupt":
        path.write_text("not a database")
    else:
        with sqlite3.connect(path) as connection:
            if state != "missing_table":
                connection.execute("CREATE TABLE providers (id TEXT PRIMARY KEY)")
            if state != "empty":
                connection.execute(f"PRAGMA user_version = {2 if state == 'wrong_version' else 1}")
    response = TestClient(create_app(Settings(database_path=path))).get("/api/health")
    assert response.status_code == (200 if state == "ready" else 503)
    if state == "ready":
        assert response.json() == {"status": "ok", "database": "ready"}


@pytest.mark.parametrize("asset", ["", "index.html", "app.js", "styles.css", "macos-tokens.css", "centers.json", "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/leaflet/LICENSE"])
def test_approved_assets_match_existing_frontend(client, asset):
    response = client.get("/" + asset)
    assert response.status_code == 200
    assert response.content == (Path(__file__).resolve().parents[2] / "frontend" / (asset or "index.html")).read_bytes()


@pytest.mark.parametrize("path", ["/backend/data/caregiving.sqlite3", "/backend/data/providers.json", "/backend/tests/test_foundation.py", "/tests/fixtures/centers.json", "/tests/acceptance.cjs", "/.env", "/.git/config", "/README.md", "/vendor/leaflet/../../tests/fixtures/centers.json", "/%2e%2e/backend/requirements.txt", "/api/unknown", "/api/app.js"])
def test_private_paths_and_unknown_api_are_not_static(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_health_is_registered_api(client):
    schema = client.get("/openapi.json").json()
    assert "/api/health" in schema["paths"]
    assert client.post("/api/health").status_code == 405


def test_search_defaults_and_trim():
    assert SearchRequest().model_dump() == dict(query="", category="all", cost="all", serviceTag=None, origin=None, radiusKm=None)
    assert SearchRequest(query="  Sector 38  ").query == "Sector 38"
    assert SearchRequest(query=" " * 130 + "abc").query == "abc"
    assert SearchRequest(origin={"latitude": 90, "longitude": -180}, radiusKm=50).radiusKm == 50


@pytest.mark.parametrize("body", [
    {"query": "x" * 121}, {"category": "hospital"}, {"cost": "cheap"},
    {"serviceTag": "other"}, {"unexpected": True}, {"radiusKm": 5},
    {"origin": {"latitude": 91, "longitude": 0}},
    {"origin": {"latitude": 0, "longitude": 181}},
    {"origin": {"latitude": float("nan"), "longitude": 0}},
    {"origin": {"latitude": 0, "longitude": float("inf")}},
    {"origin": {"latitude": 0, "longitude": 0, "accuracy": 10}},
    {"origin": {"latitude": 0, "longitude": 0}, "radiusKm": 0.9},
    {"origin": {"latitude": 0, "longitude": 0}, "radiusKm": 51},
])
def test_invalid_search_contract(body):
    with pytest.raises(ValidationError):
        SearchRequest(**body)


def test_inquiry_rejects_arbitrary_recipient():
    assert InquiryRequest().context == "general"
    assert InquiryRequest(context="vaccination").context == "vaccination"
    for body in [{"context": "booking"}, {"phone": "12345"}]:
        with pytest.raises(ValidationError):
            InquiryRequest(**body)


def test_provider_public_contract():
    provider = dict(id="sample", name="Sample", providerType="Hospital", category="health", address="Address", locality="Area", latitude=28.4, longitude=77.0, services=[], serviceTags=[], costStatus="unknown", sourceUrl="https://example.org", checkedAt="2026-10-10", coordinateStatus="Approximate area", coordinateSourceUrl="https://example.org/map")
    record = Provider(**provider)
    assert record.whatsappConfirmed is False
    assert record.distanceKm is None
    response = SearchResponse(items=[record], total=1, directoryCounts={"health": 1, "learning": 0})
    assert response.coverage == "Gurugram curated directory"
    for change in [{"latitude": 100}, {"checkedAt": "yesterday"}, {"sourceUrl": "bad"}, {"isDemo": True}, {"id": "bad id"}]:
        with pytest.raises(ValidationError):
            Provider(**(provider | change))
