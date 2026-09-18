"""
Stage 5 tests — Deterministic Compliance Engine.

Rules evaluated against simulated extracted evidence and verifications.
"""

import os
import pytest
from datetime import datetime

os.makedirs("data", exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/gemguard_test.db")

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app import models
from app.services.compliance_engine import compliance_engine

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    os.environ["DATABASE_URL"] = "sqlite:///./data/gemguard_test.db"
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_mock_bid_with_rules(db_session, bidder_category="MSME"):
    import uuid
    # Clear rules and bids
    db_session.query(models.RequirementRule).delete()
    db_session.query(models.BidPackage).delete()
    db_session.query(models.Bidder).delete()
    db_session.query(models.BidderEvidence).delete()
    db_session.query(models.VerificationRecord).delete()
    db_session.query(models.Tender).delete()
    
    tender = models.Tender(reference_number=f"TEST-{uuid.uuid4()}", title="Test", status="ACTIVE")
    db_session.add(tender)
    db_session.commit()
    
    bidder = models.Bidder(name="Test Bidder", category=bidder_category)
    db_session.add(bidder)
    db_session.commit()
    
    bid_pkg = models.BidPackage(tender_id=tender.id, bidder_id=bidder.id)
    db_session.add(bid_pkg)
    db_session.commit()
    
    # Add rules
    rule_turnover = models.RequirementRule(
        tender_id=tender.id, requirement_id="R1", rule_type="TURNOVER", metric="turnover",
        description="Turnover rule", operator="GTE", threshold_value="10.0", is_mandatory=True, applicability="ALL"
    )
    rule_gst = models.RequirementRule(
        tender_id=tender.id, requirement_id="R2", rule_type="GST_STATUS", metric="gst_status",
        description="GST rule", operator="ACTIVE", threshold_value="ACTIVE", is_mandatory=True, applicability="ALL",
        verification_sources=["GST_MOCK"]
    )
    rule_cert = models.RequirementRule(
        tender_id=tender.id, requirement_id="R3", rule_type="CERT_VALIDITY", metric="expiry_date",
        description="Cert validity", operator="VALID", threshold_value="VALID", is_mandatory=True, applicability="ALL"
    )
    rule_name = models.RequirementRule(
        tender_id=tender.id, requirement_id="R4", rule_type="NAME_MATCH", metric="entity_name",
        description="Name match", operator="MATCH", threshold_value="MATCH", is_mandatory=True, applicability="ALL"
    )
    
    db_session.add_all([rule_turnover, rule_gst, rule_cert, rule_name])
    db_session.commit()
    return bid_pkg

def add_evidence(db_session, bid_pkg_id, field, value, conf=1.0):
    doc = models.Document(bid_package_id=bid_pkg_id, filename="test.pdf")
    db_session.add(doc)
    db_session.commit()
    ev = models.BidderEvidence(
        document_id=doc.id, bid_package_id=bid_pkg_id, field=field, 
        normalized_value=value, raw_value=value, confidence=conf
    )
    db_session.add(ev)
    db_session.commit()
    return ev

def add_verification(db_session, bid_pkg_id, source, status):
    vr = models.VerificationRecord(
        bid_package_id=bid_pkg_id, source=source, source_label="Mock",
        connector_status=status, compliance_hint="PENDING" if status == "UNAVAILABLE" else "PASS_CANDIDATE",
        request_id="req-123", checked_at=datetime.utcnow()
    )
    db_session.add(vr)
    db_session.commit()
    return vr

class TestComplianceEngine:
    
    def test_numeric_threshold_pass_exact(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "turnover", "10.0")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_turnover = next(r for r in results if r.requirement_rule.rule_type == "TURNOVER")
        assert r_turnover.result == "PASS"

    def test_numeric_threshold_pass_greater(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "turnover", "12.0")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_turnover = next(r for r in results if r.requirement_rule.rule_type == "TURNOVER")
        assert r_turnover.result == "PASS"

    def test_numeric_threshold_fail_lower(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "turnover", "8.7")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_turnover = next(r for r in results if r.requirement_rule.rule_type == "TURNOVER")
        assert r_turnover.result == "FAIL"

    def test_equality_active_pass(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "gst_status", "ACTIVE")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_gst = next(r for r in results if r.requirement_rule.rule_type == "GST_STATUS")
        assert r_gst.result == "PASS"

    def test_temporal_validity_expired(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "expiry_date", "EXPIRED")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_cert = next(r for r in results if r.requirement_rule.rule_type == "CERT_VALIDITY")
        assert r_cert.result == "EXPIRED"

    def test_missing_document(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        # No evidence added at all
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_turnover = next(r for r in results if r.requirement_rule.rule_type == "TURNOVER")
        assert r_turnover.result == "MISSING"

    def test_source_unavailable_pending(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "gst_status", "ACTIVE")
        add_verification(db_session, bid_pkg.id, "GST_MOCK", "UNAVAILABLE")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_gst = next(r for r in results if r.requirement_rule.rule_type == "GST_STATUS")
        assert r_gst.result == "PENDING"

    def test_name_mismatch_review(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "entity_name", "DataVault Systems Pvt Ltd")
        add_evidence(db_session, bid_pkg.id, "entity_name", "DataVault System LLC")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_name = next(r for r in results if r.requirement_rule.rule_type == "NAME_MATCH")
        assert r_name.result == "REVIEW"

    def test_name_match_pass(self, db_session):
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "entity_name", "Test Bidder")
        add_evidence(db_session, bid_pkg.id, "entity_name", "TEST BIDDER")
        
        results = compliance_engine(db_session).evaluate_bid(bid_pkg.id)
        r_name = next(r for r in results if r.requirement_rule.rule_type == "NAME_MATCH")
        assert r_name.result == "PASS"

    def test_api_endpoint(self, db_session):
        client = TestClient(app)
        bid_pkg = create_mock_bid_with_rules(db_session)
        add_evidence(db_session, bid_pkg.id, "turnover", "10.0")
        
        response = client.post(f"/api/bids/{bid_pkg.id}/evaluate")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        r_turnover = next(r for r in data if r["requirement_rule"]["rule_type"] == "TURNOVER")
        assert r_turnover["result"] == "PASS"
