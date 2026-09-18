"""
Stage 1 backend tests: health, version, and seed data.
Run from backend/ directory: pytest tests/ -v
"""

import pytest
from fastapi.testclient import TestClient
import os
import sys

# Ensure data dir exists for test DB
os.makedirs("data", exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/gemguard_test.db")

from app.main import app
from app.database import Base, engine
import seed as seed_module


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables and seed test data once for all tests in this module."""
    # Use separate test DB
    os.environ["DATABASE_URL"] = "sqlite:///./data/gemguard_test.db"
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_module.seed()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestSystemEndpoints:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "app_name" in data
        assert "version" in data

    def test_version(self, client):
        r = client.get("/api/version")
        assert r.status_code == 200
        data = r.json()
        assert "version" in data
        assert "app_name" in data


class TestTenderEndpoints:
    def test_list_tenders(self, client):
        r = client.get("/api/tenders")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["reference_number"] == "GEM/2026/B/4521001"

    def test_get_tender(self, client):
        r = client.get("/api/tenders/1")
        assert r.status_code == 200
        data = r.json()
        assert data["turnover_threshold_cr"] == 10.0
        assert len(data["clauses"]) == 5
        assert len(data["requirement_rules"]) == 5

    def test_get_tender_not_found(self, client):
        r = client.get("/api/tenders/9999")
        assert r.status_code == 404

    def test_list_bids_for_tender(self, client):
        r = client.get("/api/tenders/1/bids")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4


class TestBidderEndpoints:
    def test_list_bidders(self, client):
        r = client.get("/api/bidders")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4
        names = [b["name"] for b in data]
        assert any("Bidder A" in n for n in names)
        assert any("Bidder B" in n for n in names)

    def test_get_bidder(self, client):
        r = client.get("/api/bidders/1")
        assert r.status_code == 200
        data = r.json()
        assert "gstin" in data
        assert "turnover_cr" in data

    def test_get_bidder_not_found(self, client):
        r = client.get("/api/bidders/9999")
        assert r.status_code == 404


class TestBidEndpoints:
    def test_list_bids(self, client):
        r = client.get("/api/bids")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4

    def test_get_bid(self, client):
        r = client.get("/api/bids/1")
        assert r.status_code == 200
        data = r.json()
        assert "overall_status" in data
        assert "bidder" in data

    def test_officer_action_valid(self, client):
        r = client.post("/api/bids/1/officer-action", json={
            "officer_id": "test_officer",
            "action": "APPROVED",
            "comment": "Test approval",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == "APPROVED"

    def test_officer_action_invalid(self, client):
        r = client.post("/api/bids/1/officer-action", json={
            "officer_id": "test_officer",
            "action": "INVALID_ACTION",
        })
        assert r.status_code == 400


class TestAuditEndpoints:
    def test_get_audit_trail(self, client):
        r = client.get("/api/audit/1")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        event_types = [e["event_type"] for e in data]
        assert "BID_SUBMITTED" in event_types
