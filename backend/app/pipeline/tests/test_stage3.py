"""
Stage 3 tests: document pipeline, entity extraction, upload/evidence endpoints.

Run from backend/ directory:  pytest tests/test_stage3.py -v

ACCEPTANCE:
  Upload demo_ca_certificate_bidder_b.pdf → evidence shows turnover=8.7 from page 4
"""

import io
import os
import sys
import pytest

os.makedirs("data", exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/gemguard_test.db")

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
from app.services.entity_extractor import EntityExtractor, ExtractedField
from app.services.document_pipeline import classify_document
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


# ── Entity Extractor ─────────────────────────────────────────────────────────────

class TestEntityExtractor:
    def setup_method(self):
        self.ex = EntityExtractor()

    def test_extracts_turnover_crore(self):
        text = "The average annual turnover of not less than Rs. 8.7 Crore for the last three years."
        fields = self.ex.extract(text)
        turnover = [f for f in fields if f.field == "turnover_avg_3fy"]
        assert turnover, "Should extract turnover"
        assert turnover[0].normalized_value == "8.7"

    def test_extracts_turnover_symbol(self):
        text = "AVERAGE ANNUAL TURNOVER: ₹8.7 Crore"
        fields = self.ex.extract(text)
        turnover = [f for f in fields if f.field == "turnover_avg_3fy"]
        assert turnover
        assert turnover[0].normalized_value == "8.7"

    def test_turnover_raw_value_preserved(self):
        text = "The annual turnover is Rs. 14.2 Crore as per audited accounts."
        fields = self.ex.extract(text)
        t = next((f for f in fields if f.field == "turnover_avg_3fy"), None)
        assert t is not None
        assert "14.2" in t.raw_value or "14.2" in str(t.normalized_value)

    def test_extracts_gst_active(self):
        text = "GST Registration Status: ACTIVE"
        fields = self.ex.extract(text)
        gst = [f for f in fields if f.field == "gst_registration_status"]
        assert gst
        assert gst[0].normalized_value == "ACTIVE"

    def test_extracts_udyam_number(self):
        text = "Udyam Registration Number: UDYAM-DL-03-0067891"
        fields = self.ex.extract(text)
        udyam = [f for f in fields if f.field == "udyam_number"]
        assert udyam
        assert udyam[0].normalized_value == "UDYAM-DL-03-0067891"

    def test_extracts_entity_name(self):
        text = "Name of the firm: Infralink Technologies Limited\nRegistered Address: New Delhi"
        fields = self.ex.extract(text)
        names = [f for f in fields if f.field == "legal_entity_name"]
        assert names
        assert "Infralink" in names[0].normalized_value

    def test_extracts_issue_date(self):
        text = "Date of Issue: 15/03/2026"
        fields = self.ex.extract(text)
        dates = [f for f in fields if f.field == "certificate_issue_date"]
        assert dates
        assert "15/03/2026" in dates[0].normalized_value

    def test_extracts_expiry_date(self):
        text = "Valid upto: 31/12/2026"
        fields = self.ex.extract(text)
        dates = [f for f in fields if f.field == "certificate_expiry_date"]
        assert dates
        assert "31/12/2026" in dates[0].normalized_value

    def test_extracts_gstin(self):
        text = "GSTIN: 07AACCI4520M1ZP"
        fields = self.ex.extract(text)
        gstins = [f for f in fields if f.field == "gstin"]
        assert gstins
        assert gstins[0].normalized_value == "07AACCI4520M1ZP"

    def test_no_crash_empty_text(self):
        fields = self.ex.extract("")
        assert fields == []

    def test_no_crash_irrelevant_text(self):
        text = "This document contains no relevant financial information."
        fields = self.ex.extract(text)
        # May extract nothing — must not crash
        assert isinstance(fields, list)

    def test_confidence_is_extraction_only(self):
        """Confidence must be in 0-1 range. It is NOT a compliance score."""
        text = "The average annual turnover of Rs. 8.7 Crore. GST Status: ACTIVE"
        fields = self.ex.extract(text)
        for f in fields:
            assert 0.0 <= f.confidence <= 1.0, f"Confidence out of range for {f.field}: {f.confidence}"

    def test_low_confidence_sets_review_status(self):
        """Fields extracted with low confidence should be marked REVIEW."""
        # Direct test of _status function
        from app.services.entity_extractor import _status
        assert _status(0.4) == "REVIEW"
        assert _status(0.2) == "MANUAL_REQUIRED"
        assert _status(0.9) == "UNVERIFIED"

    def test_source_page_returned(self):
        """Source page number must be returned."""
        text = "The average annual turnover of Rs. 8.7 Crore"
        fields = self.ex.extract(text)
        for f in fields:
            assert f.source_page is not None


# ── Document Classification ────────────────────────────────────────────────────

class TestDocumentClassification:
    def test_classify_ca_certificate(self):
        text = "chartered accountant average annual turnover certificate profit & loss"
        doc_type, conf = classify_document(text)
        assert doc_type == "CA_CERTIFICATE"
        assert conf > 0.5

    def test_classify_gst_certificate(self):
        text = "goods and services tax registration GSTIN certificate of registration GST"
        doc_type, conf = classify_document(text)
        assert doc_type == "GST_CERTIFICATE"
        assert conf > 0.5

    def test_classify_udyam(self):
        text = "udyam registration certificate ministry of msme UDYAM-DL-03-0067891"
        doc_type, conf = classify_document(text)
        assert doc_type == "UDYAM_CERTIFICATE"

    def test_classify_unknown(self):
        doc_type, conf = classify_document("random text with no keywords")
        assert doc_type == "UNKNOWN"

    def test_confidence_in_range(self):
        _, conf = classify_document("chartered accountant turnover")
        assert 0.0 <= conf <= 1.0


# ── Upload Endpoint ─────────────────────────────────────────────────────────────

def _make_minimal_pdf(text: str = "Test document") -> bytes:
    """Create minimal valid PDF bytes for testing."""
    content = f"% This is a test document\n{text}"
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n9\n%%EOF"
    )


class TestDocumentUpload:
    def test_upload_rejects_empty_file(self, client):
        r = client.post(
            "/api/bids/1/documents/upload",
            files={"file": ("test.pdf", b"", "application/pdf")},
        )
        assert r.status_code == 400

    def test_upload_rejects_non_pdf(self, client):
        r = client.post(
            "/api/bids/1/documents/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert r.status_code == 400

    def test_upload_invalid_bid(self, client):
        r = client.post(
            "/api/bids/9999/documents/upload",
            files={"file": ("test.pdf", _make_minimal_pdf(), "application/pdf")},
        )
        assert r.status_code == 404

    def test_upload_valid_pdf_returns_document(self, client):
        r = client.post(
            "/api/bids/1/documents/upload",
            files={"file": ("test_cert.pdf", _make_minimal_pdf(), "application/pdf")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["bid_package_id"] == 1
        assert data["original_filename"] == "test_cert.pdf"
        assert data["file_hash"] is not None
        assert data["pipeline_status"] in ("PROCESSED", "FAILED", "PENDING")

    def test_upload_processes_pipeline(self, client):
        r = client.post(
            "/api/bids/1/documents/upload",
            files={"file": ("test_cert.pdf", _make_minimal_pdf(), "application/pdf")},
        )
        assert r.status_code == 200
        data = r.json()
        # Pipeline must run (status not PENDING after processing)
        assert data["pipeline_status"] in ("PROCESSED", "FAILED")
        # Evidence list must be present (may be empty for minimal PDF)
        assert "bidder_evidence" in data
        assert isinstance(data["bidder_evidence"], list)


# ── Evidence from CA Certificate ──────────────────────────────────────────────

class TestCAEvidenceExtraction:
    """
    Upload the demo CA certificate and verify:
      - doc_type = CA_CERTIFICATE
      - turnover_avg_3fy extracted = 8.7
      - source_page = 4
    """

    @pytest.fixture(scope="class")
    def uploaded_doc(self, client):
        ca_path = "data/bidder_docs/demo_ca_certificate_bidder_b.pdf"
        if not os.path.exists(ca_path):
            # Generate it
            import create_demo_bidder_docs
            create_demo_bidder_docs.create_pdf_from_pages(
                create_demo_bidder_docs.CA_CERT_PAGES,
                ca_path,
                "CA Certificate — Infralink Technologies Limited",
            )
        with open(ca_path, "rb") as f:
            pdf_bytes = f.read()
        r = client.post(
            "/api/bids/2/documents/upload",  # Bidder B = bid 2
            files={"file": ("demo_ca_certificate_bidder_b.pdf", pdf_bytes, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_doc_type_is_ca_certificate(self, uploaded_doc):
        assert uploaded_doc["doc_type"] == "CA_CERTIFICATE"

    def test_pipeline_processed(self, uploaded_doc):
        assert uploaded_doc["pipeline_status"] == "PROCESSED"

    def test_turnover_extracted(self, uploaded_doc):
        evidence = uploaded_doc["bidder_evidence"]
        turnover_ev = [e for e in evidence if e["field"] == "turnover_avg_3fy"]
        assert turnover_ev, f"No turnover evidence found. All fields: {[e['field'] for e in evidence]}"
        assert turnover_ev[0]["normalized_value"] == "8.7"

    def test_turnover_on_page_4(self, uploaded_doc):
        evidence = uploaded_doc["bidder_evidence"]
        turnover_ev = [e for e in evidence if e["field"] == "turnover_avg_3fy"]
        assert turnover_ev
        # The highest confidence turnover should be on page 4
        best = max(turnover_ev, key=lambda e: e.get("confidence", 0))
        assert best["source_page"] == 4, f"Expected page 4, got {best['source_page']}"

    def test_raw_value_contains_crore(self, uploaded_doc):
        evidence = uploaded_doc["bidder_evidence"]
        turnover_ev = [e for e in evidence if e["field"] == "turnover_avg_3fy"]
        assert turnover_ev
        best = max(turnover_ev, key=lambda e: e.get("confidence", 0))
        raw = (best["raw_value"] or "").lower()
        assert "crore" in raw or "cr" in raw or "8.7" in raw

    def test_evidence_has_source_snippet(self, uploaded_doc):
        evidence = uploaded_doc["bidder_evidence"]
        for ev in evidence:
            if ev["source_snippet"] is not None:
                assert len(ev["source_snippet"]) > 0

    def test_confidence_not_compliance_status(self, uploaded_doc):
        """Confidence is extraction quality only — not compliance."""
        evidence = uploaded_doc["bidder_evidence"]
        for ev in evidence:
            if ev["confidence"] is not None:
                assert 0.0 <= ev["confidence"] <= 1.0
            # verification_status must be one of the defined states
            assert ev["verification_status"] in (
                "UNVERIFIED", "VERIFIED", "REVIEW", "MANUAL_REQUIRED"
            )


# ── Evidence API ──────────────────────────────────────────────────────────────

class TestEvidenceAPI:
    def test_list_bid_documents(self, client):
        r = client.get("/api/bids/1/documents")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_bid_evidence(self, client):
        r = client.get("/api/bids/2/evidence")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_evidence_item(self, client):
        # Get any evidence item
        r = client.get("/api/bids/2/evidence")
        evidence = r.json()
        if evidence:
            ev_id = evidence[0]["id"]
            r2 = client.get(f"/api/evidence/{ev_id}")
            assert r2.status_code == 200
            data = r2.json()
            assert data["id"] == ev_id
            assert "field" in data
            assert "raw_value" in data
            assert "normalized_value" in data
            assert "source_page" in data
            assert "confidence" in data
            assert "verification_status" in data

    def test_get_nonexistent_evidence(self, client):
        r = client.get("/api/evidence/99999")
        assert r.status_code == 404

    def test_get_bid_document_detail(self, client):
        r = client.get("/api/bids/1/documents")
        docs = r.json()
        if docs:
            doc_id = docs[0]["id"]
            r2 = client.get(f"/api/bids/1/documents/{doc_id}")
            assert r2.status_code == 200
            data = r2.json()
            assert "bidder_evidence" in data
            assert isinstance(data["bidder_evidence"], list)
