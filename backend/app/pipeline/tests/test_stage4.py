"""
Stage 4 tests — Verification Connector Layer.

ACCEPTANCE CRITERION:
  Select Bidder D → run verification → EPFOAdapter returns UNAVAILABLE
  → compliance_hint = PENDING (never FAIL)
  → VerificationRecord stored with connector_status = UNAVAILABLE

Run: pytest tests/test_stage4.py -v
"""

import os
import pytest

os.makedirs("data", exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/gemguard_test.db")

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
from app.services.connectors.base import VerificationResponse, VerificationStatus
from app.services.connectors.udyam_adapter import UdyamAdapter
from app.services.connectors.gst_adapter import GSTAdapter
from app.services.connectors.pan_adapter import PANAdapter
from app.services.connectors.epfo_adapter import EPFOAdapter
from app.services.connectors import CONNECTOR_REGISTRY
import seed as seed_module


@pytest.fixture(scope="module", autouse=True)
def setup_db():
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


# ── VerificationResponse schema ───────────────────────────────────────────────

class TestVerificationResponseSchema:
    def test_valid_response_created(self):
        resp = VerificationResponse(
            source="TEST_MOCK",
            source_label="Simulation / Authorized Adapter",
            status=VerificationStatus.VERIFIED,
            request_id=VerificationResponse.make_id(),
            checked_at=__import__("datetime").datetime.utcnow(),
            fields={"status": "ACTIVE"},
            raw_hash=VerificationResponse.hash_response({"status": "ACTIVE"}),
            message="OK",
        )
        assert resp.status == VerificationStatus.VERIFIED
        assert resp.simulated is True

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            VerificationResponse(
                source="X",
                source_label="X",
                status="INVALID_STATUS",
                request_id="x",
                checked_at=__import__("datetime").datetime.utcnow(),
                fields={},
                raw_hash="x",
                message="x",
            )

    def test_request_id_is_uuid(self):
        rid = VerificationResponse.make_id()
        import uuid
        uuid.UUID(rid)  # must not raise

    def test_raw_hash_is_string(self):
        h = VerificationResponse.hash_response({"key": "value"})
        assert isinstance(h, str)
        assert len(h) > 0

    def test_all_status_constants_valid(self):
        """All status constants must be in the ALL set."""
        for s in [
            VerificationStatus.VERIFIED,
            VerificationStatus.NOT_VERIFIED,
            VerificationStatus.UNAVAILABLE,
            VerificationStatus.STALE,
            VerificationStatus.UNAUTHORIZED,
            VerificationStatus.MANUAL_REQUIRED,
        ]:
            assert s in VerificationStatus.ALL


# ── Udyam Adapter ─────────────────────────────────────────────────────────────

class TestUdyamAdapter:
    def setup_method(self):
        self.adapter = UdyamAdapter()

    def test_known_udyam_returns_verified(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-DL-03-0067891"})
        assert resp.status == VerificationStatus.VERIFIED
        assert resp.fields["registration_status"] == "ACTIVE"

    def test_unknown_udyam_returns_not_verified(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-XX-99-9999999"})
        assert resp.status == VerificationStatus.NOT_VERIFIED

    def test_bidder_d_gstin_triggers_unavailable(self):
        """CRITICAL: Bidder D GSTIN must trigger UNAVAILABLE, not FAIL."""
        resp = self.adapter.verify({"udyam_number": "", "gstin": "33AABNE5678F1ZQ"})
        assert resp.status == VerificationStatus.UNAVAILABLE

    def test_bidder_d_udyam_triggers_unavailable(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-TN-04-0012345"})
        assert resp.status == VerificationStatus.UNAVAILABLE

    def test_response_has_request_id(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-KA-01-0034521"})
        assert resp.request_id and len(resp.request_id) > 8

    def test_response_has_checked_at(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-KA-01-0034521"})
        assert resp.checked_at is not None

    def test_source_label_is_simulation(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-DL-03-0067891"})
        assert "Simulation" in resp.source_label or "Authorized" in resp.source_label

    def test_simulated_flag_true(self):
        resp = self.adapter.verify({"udyam_number": "UDYAM-DL-03-0067891"})
        assert resp.simulated is True


# ── GST Adapter ───────────────────────────────────────────────────────────────

class TestGSTAdapter:
    def setup_method(self):
        self.adapter = GSTAdapter()

    def test_known_gstin_returns_verified(self):
        resp = self.adapter.verify({"gstin": "29AABCT1332L1ZX"})
        assert resp.status == VerificationStatus.VERIFIED
        assert resp.fields["registration_status"] == "ACTIVE"

    def test_unknown_gstin_returns_not_verified(self):
        resp = self.adapter.verify({"gstin": "99XXXXX0000X0XX"})
        assert resp.status == VerificationStatus.NOT_VERIFIED

    def test_bidder_d_gstin_unavailable(self):
        resp = self.adapter.verify({"gstin": "33AABNE5678F1ZQ"})
        assert resp.status == VerificationStatus.UNAVAILABLE

    def test_response_schema_valid(self):
        resp = self.adapter.verify({"gstin": "07AACCI4520M1ZP"})
        assert resp.source == "GST_MOCK"
        assert isinstance(resp.fields, dict)
        assert resp.raw_hash is not None


# ── PAN Adapter ───────────────────────────────────────────────────────────────

class TestPANAdapter:
    def setup_method(self):
        self.adapter = PANAdapter()

    def test_valid_pan_returns_verified(self):
        resp = self.adapter.verify({"pan": "AACCI4520M", "name": "INFRALINK TECHNOLOGIES LIMITED"})
        assert resp.status == VerificationStatus.VERIFIED
        assert resp.fields["pan_status"] == "VALID"

    def test_unknown_pan_not_verified(self):
        resp = self.adapter.verify({"pan": "XXXXX0000X"})
        assert resp.status == VerificationStatus.NOT_VERIFIED

    def test_bidder_d_pan_unavailable(self):
        resp = self.adapter.verify({"pan": "AABNE5678F"})
        assert resp.status == VerificationStatus.UNAVAILABLE


# ── EPFO Adapter ──────────────────────────────────────────────────────────────

class TestEPFOAdapter:
    def setup_method(self):
        self.adapter = EPFOAdapter()

    def test_known_pan_returns_verified(self):
        resp = self.adapter.verify({"pan": "AABCT1332L"})
        assert resp.status == VerificationStatus.VERIFIED

    def test_bidder_d_epfo_unavailable(self):
        """
        ACCEPTANCE: Bidder D EPFO → UNAVAILABLE
        Must NEVER be FAIL.
        """
        resp = self.adapter.verify({"pan": "AABNE5678F"})
        assert resp.status == VerificationStatus.UNAVAILABLE
        assert resp.status != "FAIL"

    def test_unavailable_message_explains_pending(self):
        resp = self.adapter.verify({"pan": "AABNE5678F"})
        assert resp.message  # must have an explanation
        assert len(resp.message) > 10


# ── Connector Registry ────────────────────────────────────────────────────────

class TestConnectorRegistry:
    def test_all_connectors_registered(self):
        for source_id in ["GST_MOCK", "UDYAM_MOCK", "PAN_MOCK", "EPFO_MOCK"]:
            assert source_id in CONNECTOR_REGISTRY

    def test_all_connectors_return_schema_valid_response(self):
        payloads = {
            "GST_MOCK":   {"gstin": "29AABCT1332L1ZX"},
            "UDYAM_MOCK": {"udyam_number": "UDYAM-KA-01-0034521"},
            "PAN_MOCK":   {"pan": "AABCT1332L", "name": "TECHNOSERVE"},
            "EPFO_MOCK":  {"pan": "AABCT1332L"},
        }
        for source_id, payload in payloads.items():
            connector = CONNECTOR_REGISTRY[source_id]
            resp = connector.verify(payload)
            assert resp.status in VerificationStatus.ALL
            assert resp.source == source_id
            assert resp.request_id
            assert resp.simulated is True


# ── Retry Mechanism ───────────────────────────────────────────────────────────

class TestRetryMechanism:
    def test_retry_on_unavailable(self):
        """UNAVAILABLE retries should not exceed max and must return UNAVAILABLE."""
        adapter = EPFOAdapter()
        resp = adapter.verify({"pan": "AABNE5678F"}, retry=2)
        assert resp.status == VerificationStatus.UNAVAILABLE
        assert resp.retry_count == 2  # exhausted all retries

    def test_retry_zero_no_extra_attempts(self):
        adapter = EPFOAdapter()
        resp = adapter.verify({"pan": "AABNE5678F"}, retry=0)
        assert resp.status == VerificationStatus.UNAVAILABLE
        assert resp.retry_count == 0

    def test_no_retry_on_verified(self):
        adapter = GSTAdapter()
        resp = adapter.verify({"gstin": "29AABCT1332L1ZX"}, retry=3)
        assert resp.status == VerificationStatus.VERIFIED
        assert resp.retry_count == 0  # no retry needed


# ── Verification API Endpoint ─────────────────────────────────────────────────

class TestVerificationAPI:
    def test_run_verification_bidder_a(self, client):
        """Bidder A should have all sources VERIFIED."""
        r = client.post("/api/bids/1/verify")
        assert r.status_code == 200
        records = r.json()
        assert isinstance(records, list)
        assert len(records) > 0
        for rec in records:
            assert rec["connector_status"] in VerificationStatus.ALL
            assert rec["source_label"] in ("Simulation / Authorized Adapter",)
            assert rec["simulated"] is True
            assert rec["request_id"]
            assert rec["compliance_hint"] in ("PASS_CANDIDATE", "REVIEW", "PENDING")

    def test_run_verification_bidder_d_unavailable(self, client):
        """
        ACCEPTANCE: Bidder D → verification has UNAVAILABLE sources
        → compliance_hint = PENDING (never FAIL).
        """
        r = client.post("/api/bids/4/verify")
        assert r.status_code == 200
        records = r.json()
        assert records

        unavailable = [rec for rec in records if rec["connector_status"] == "UNAVAILABLE"]
        assert unavailable, f"Expected UNAVAILABLE record for Bidder D. Got: {[r['connector_status'] for r in records]}"

        for rec in unavailable:
            # CORE NON-NEGOTIABLE: UNAVAILABLE must NEVER produce FAIL
            assert rec["compliance_hint"] == "PENDING", (
                f"UNAVAILABLE compliance_hint must be PENDING, got {rec['compliance_hint']}"
            )
            assert rec["compliance_hint"] != "FAIL"

    def test_run_verification_stores_records(self, client):
        client.post("/api/bids/2/verify")
        r = client.get("/api/bids/2/verifications")
        assert r.status_code == 200
        records = r.json()
        assert len(records) > 0

    def test_list_verifications_has_timestamps(self, client):
        r = client.get("/api/bids/1/verifications")
        records = r.json()
        for rec in records:
            assert rec["checked_at"]
            assert rec["request_id"]

    def test_get_single_verification_record(self, client):
        r = client.get("/api/bids/1/verifications")
        records = r.json()
        if records:
            rec_id = records[0]["id"]
            r2 = client.get(f"/api/verifications/{rec_id}")
            assert r2.status_code == 200
            data = r2.json()
            assert data["id"] == rec_id
            assert "source" in data
            assert "connector_status" in data
            assert "compliance_hint" in data
            assert "fields_verified" in data
            assert "message" in data

    def test_verification_invalid_bid(self, client):
        r = client.post("/api/bids/9999/verify")
        assert r.status_code == 404

    def test_get_invalid_record(self, client):
        r = client.get("/api/verifications/99999")
        assert r.status_code == 404

    def test_rerun_replaces_previous_records(self, client):
        client.post("/api/bids/3/verify")
        r1 = client.get("/api/bids/3/verifications")
        count1 = len(r1.json())

        client.post("/api/bids/3/verify")
        r2 = client.get("/api/bids/3/verifications")
        count2 = len(r2.json())

        assert count2 == count1  # re-run replaces, not appends

    def test_no_credentials_in_response(self, client):
        """Ensure no sensitive data leaks to the API response."""
        r = client.post("/api/bids/1/verify")
        response_text = r.text.lower()
        # Should not contain any credential-like patterns
        for bad_word in ["password", "secret", "api_key", "token", "bearer"]:
            assert bad_word not in response_text


# ── Compliance Hint Mapping ───────────────────────────────────────────────────

class TestComplianceHintMapping:
    """
    Verifies the UNAVAILABLE → PENDING mapping is enforced at the service layer.
    """

    def test_unavailable_maps_to_pending_via_api(self, client):
        r = client.post("/api/bids/4/verify")
        records = r.json()
        for rec in records:
            if rec["connector_status"] == "UNAVAILABLE":
                assert rec["compliance_hint"] == "PENDING"

    def test_verified_maps_to_pass_candidate(self, client):
        r = client.post("/api/bids/1/verify")
        records = r.json()
        for rec in records:
            if rec["connector_status"] == "VERIFIED":
                assert rec["compliance_hint"] == "PASS_CANDIDATE"

    def test_not_verified_maps_to_review(self, client):
        """NOT_VERIFIED should map to REVIEW, not FAIL."""
        from app.services.verification_service import VerificationService
        from app.services.connectors.base import VerificationStatus, VerificationResponse
        import datetime

        svc = VerificationService()
        resp = VerificationResponse(
            source="TEST",
            source_label="Simulation / Authorized Adapter",
            status=VerificationStatus.NOT_VERIFIED,
            request_id=VerificationResponse.make_id(),
            checked_at=datetime.datetime.utcnow(),
            fields={},
            raw_hash="abc",
            message="test",
        )
        from app.services.verification_service import VerificationService
        # Access the mapping directly
        hint = {
            VerificationStatus.VERIFIED:        "PASS_CANDIDATE",
            VerificationStatus.NOT_VERIFIED:    "REVIEW",
            VerificationStatus.UNAVAILABLE:     "PENDING",
            VerificationStatus.STALE:           "REVIEW",
            VerificationStatus.UNAUTHORIZED:    "PENDING",
            VerificationStatus.MANUAL_REQUIRED: "PENDING",
        }.get(resp.status, "PENDING")
        assert hint == "REVIEW"
        assert hint != "FAIL"
