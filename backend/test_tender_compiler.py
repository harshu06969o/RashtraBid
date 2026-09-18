"""
Test Suite for Tender AI Compiler & Rules Router
Validates:
1. PyMuPDF PDF Ingestion with Text & Table Parsing
2. Rule Extraction Engine (Turnover, MII %, Statutory: GST, PAN, Udyam)
3. POST /api/v1/tenders/upload endpoint
4. PUT /api/v1/tenders/{id}/rules Procurement Officer manual override
"""

import asyncio
import io
import json
from datetime import datetime, timezone
from fpdf import FPDF
from fastapi.testclient import TestClient

from app.core.database import connect_to_mongo, close_mongo_connection, get_db
from app.pipeline.tender_compiler import (
    TenderCompiler,
    TenderPDFParser,
    RuleExtractionEngine,
)
from app.schemas.domain import RequirementRule, RuleStatus, RuleSeverity
from app.main import app

passed = 0
failed = 0


def assert_test(condition: bool, message: str):
    global passed, failed
    if condition:
        print(f"  [PASS] {message}")
        passed += 1
    else:
        print(f"  [FAIL] {message}")
        failed += 1


def create_sample_tender_pdf() -> bytes:
    """Generate a realistic test PDF with text clauses and a table structure."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "GOVERNMENT e-MARKETPLACE (GeM)", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Tender Reference: GEM/2026/B/4521001", ln=True, align="C")
    pdf.cell(0, 8, "Issuing Authority: Chennai Petroleum Corporation Limited (CPCL)", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "SECTION 3 -- ELIGIBILITY CRITERIA & MANDATORY CLAUSES", ln=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, "Clause 3.1 Financial Turnover: The bidder must have an average annual turnover of not less than Rs. 14.2 Crore during the last three financial years, certified by a Chartered Accountant.")
    pdf.ln(2)

    pdf.multi_cell(0, 6, "Clause 3.2 GST Compliance: The bidder must hold an ACTIVE Goods and Services Tax (GST) registration certificate under the GST Act, 2017.")
    pdf.ln(2)

    pdf.multi_cell(0, 6, "Clause 3.3 MSME / Udyam Registration: MSME bidders must hold a valid Udyam Registration Certificate with active URN.")
    pdf.ln(2)

    pdf.multi_cell(0, 6, "Clause 3.4 Local Content (Make in India): In accordance with Public Procurement Order, Class-I local suppliers must have minimum 50% local content.")
    pdf.ln(2)

    pdf.multi_cell(0, 6, "Clause 3.5 PAN Validity: The bidder must possess a valid Permanent Account Number (PAN) issued by the Income Tax Department.")
    pdf.ln(5)

    # Add Table Structure
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Summary of Mandatory Criteria Table:", ln=True)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(35, 7, "Criterion", border=1)
    pdf.cell(35, 7, "Required Metric", border=1)
    pdf.cell(40, 7, "Minimum Threshold", border=1)
    pdf.cell(40, 7, "Document Proof", border=1, ln=True)

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(35, 6, "Financial", border=1)
    pdf.cell(35, 6, "Annual Turnover", border=1)
    pdf.cell(40, 6, "Rs. 14.2 Cr", border=1)
    pdf.cell(40, 6, "CA Certificate", border=1, ln=True)

    pdf.cell(35, 6, "Statutory GST", border=1)
    pdf.cell(35, 6, "GST Registration", border=1)
    pdf.cell(40, 6, "ACTIVE status", border=1)
    pdf.cell(40, 6, "GST REG-06", border=1, ln=True)

    pdf.cell(35, 6, "Statutory PAN", border=1)
    pdf.cell(35, 6, "PAN Card", border=1)
    pdf.cell(40, 6, "VALID", border=1)
    pdf.cell(40, 6, "PAN Card Copy", border=1, ln=True)

    pdf.cell(35, 6, "Local Content", border=1)
    pdf.cell(35, 6, "Make in India", border=1)
    pdf.cell(40, 6, "50% MII Content", border=1)
    pdf.cell(40, 6, "MII Declaration", border=1, ln=True)

    pdf.cell(35, 6, "MSME Proof", border=1)
    pdf.cell(35, 6, "Udyam Certificate", border=1)
    pdf.cell(40, 6, "ACTIVE URN", border=1)
    pdf.cell(40, 6, "Udyam Certificate", border=1, ln=True)

    return bytes(pdf.output())


def test_pdf_parsing_and_table_extraction(pdf_bytes: bytes):
    print("\n--- 1. Testing PyMuPDF Parsing & Table Structure Capture ---")
    parsed = TenderPDFParser.parse_pdf(pdf_bytes)

    assert_test(parsed.total_pages >= 1, f"Parsed total pages: {parsed.total_pages}")
    assert_test("GEM/2026/B/4521001" in parsed.full_text, "Tender Reference extracted in full text")
    assert_test("Clause 3.1" in parsed.full_text, "Clause 3.1 text extracted")
    assert_test(len(parsed.tables) >= 1, f"Extracted {len(parsed.tables)} table structure(s)")

    # Check table structure
    if parsed.tables:
        tbl = parsed.tables[0]
        assert_test(len(tbl.headers) >= 3, f"Table has {len(tbl.headers)} headers: {tbl.headers}")
        assert_test(len(tbl.rows) >= 3, f"Table has {len(tbl.rows)} data rows")
        assert_test("|" in tbl.markdown, "Table converted to structured Markdown")

    # Check extracted metadata
    assert_test(parsed.metadata.get("tender_no") == "GEM/2026/B/4521001", f"Tender No detected: {parsed.metadata.get('tender_no')}")
    assert_test("CPCL" in parsed.metadata.get("organization", ""), f"Organization detected: {parsed.metadata.get('organization')}")


def test_rule_extraction_engine(pdf_bytes: bytes):
    print("\n--- 2. Testing Rule Extraction Engine (Turnover, MII %, Statutory) ---")
    parsed = TenderPDFParser.parse_pdf(pdf_bytes)
    engine = RuleExtractionEngine(tender_id="tender_test_001")
    rules = engine.extract_rules(parsed)

    assert_test(len(rules) >= 5, f"Extracted {len(rules)} compliance rules")

    # Group rules by metric
    by_metric = {r.metric: r for r in rules}

    # 1. Turnover
    turnover_rule = by_metric.get("annual_turnover_cr")
    assert_test(turnover_rule is not None, "Extracted 'annual_turnover_cr' rule")
    if turnover_rule:
        assert_test(turnover_rule.threshold == 14.2, f"Turnover threshold correctly parsed as 14.2 Cr (got {turnover_rule.threshold})")
        assert_test(turnover_rule.operator == ">=", f"Turnover operator is '>=' (got {turnover_rule.operator})")
        assert_test(turnover_rule.severity == "CRITICAL", "Turnover severity is CRITICAL")
        assert_test(turnover_rule.evidence_type == "CA_CERTIFICATE", "Turnover evidence type is CA_CERTIFICATE")

    # 2. Make in India %
    mii_rule = by_metric.get("mii_local_content_percentage")
    assert_test(mii_rule is not None, "Extracted 'mii_local_content_percentage' rule")
    if mii_rule:
        assert_test(mii_rule.threshold == 50.0, f"MII threshold correctly parsed as 50% (got {mii_rule.threshold})")
        assert_test(mii_rule.operator == ">=", f"MII operator is '>=' (got {mii_rule.operator})")
        assert_test(mii_rule.unit == "%", f"MII unit is '%' (got {mii_rule.unit})")

    # 3. GST
    gst_rule = by_metric.get("gst_registration_active")
    assert_test(gst_rule is not None, "Extracted 'gst_registration_active' statutory rule")
    if gst_rule:
        assert_test(gst_rule.threshold is True, "GST threshold is True (active required)")
        assert_test(gst_rule.evidence_type == "GST_CERTIFICATE", "GST evidence type is GST_CERTIFICATE")

    # 4. PAN
    pan_rule = by_metric.get("pan_card_valid")
    assert_test(pan_rule is not None, "Extracted 'pan_card_valid' statutory rule")
    if pan_rule:
        assert_test(pan_rule.threshold is True, "PAN threshold is True (valid required)")
        assert_test(pan_rule.evidence_type == "PAN_CARD", "PAN evidence type is PAN_CARD")

    # 5. Udyam
    udyam_rule = by_metric.get("udyam_registration_active")
    assert_test(udyam_rule is not None, "Extracted 'udyam_registration_active' statutory rule")
    if udyam_rule:
        assert_test(udyam_rule.threshold is True, "Udyam threshold is True (active required)")
        assert_test(udyam_rule.evidence_type == "UDYAM_CERTIFICATE", "Udyam evidence type is UDYAM_CERTIFICATE")


def test_api_endpoints(pdf_bytes: bytes):
    print("\n--- 3. Testing FastAPI Endpoints (POST upload & PUT manual override) ---")
    client = TestClient(app, base_url="http://testserver")

    # Test POST /api/v1/tenders/upload
    files = {
        "file": ("tender_gem_4521001.pdf", pdf_bytes, "application/pdf")
    }
    upload_res = client.post("/api/v1/tenders/upload", files=files)
    assert_test(upload_res.status_code == 200, f"POST /api/v1/tenders/upload returned 200 (got {upload_res.status_code})")

    data = upload_res.json()
    assert_test(data.get("status") == "success", "Upload response status is 'success'")
    tender = data.get("tender", {})
    tender_id = tender.get("id")
    assert_test(bool(tender_id), f"Tender created with ID: {tender_id}")
    assert_test(tender.get("tender_no") == "GEM/2026/B/4521001", f"Tender No matches: {tender.get('tender_no')}")
    assert_test("CPCL" in tender.get("organization", ""), f"Organization set to CPCL: {tender.get('organization')}")

    rules = data.get("rules", [])
    assert_test(len(rules) >= 5, f"Response contains {len(rules)} compiled rules")

    # Test PUT /api/v1/tenders/{tender_id}/rules (Manual Officer Override)
    print("\n--- 4. Testing Manual Override (PUT /api/v1/tenders/{id}/rules) ---")
    modified_rules = [
        {
            "clause_id": "Clause 3.1-OVERRIDE",
            "metric": "annual_turnover_cr",
            "operator": ">=",
            "threshold": 16.0,  # Adjusted from 14.2 to 16.0 Cr
            "unit": "INR_CR",
            "severity": "CRITICAL",
            "evidence_type": "CA_CERTIFICATE",
        },
        {
            "clause_id": "Clause 3.4-OVERRIDE",
            "metric": "mii_local_content_percentage",
            "operator": ">=",
            "threshold": 60.0,  # Adjusted from 50% to 60%
            "unit": "%",
            "severity": "CRITICAL",
            "evidence_type": "MII_DECLARATION",
        },
        {
            "clause_id": "Clause 3.2",
            "metric": "gst_registration_active",
            "operator": "==",
            "threshold": True,
            "unit": "BOOLEAN",
            "severity": "CRITICAL",
            "evidence_type": "GST_CERTIFICATE",
        },
    ]

    override_payload = {
        "rules": modified_rules,
        "actor": "officer@gem.gov.in",
        "reason": "Increased minimum turnover to 16 Cr and MII to 60% per CPCL board directive.",
    }

    override_res = client.put(f"/api/v1/tenders/{tender_id}/rules", json=override_payload)
    assert_test(override_res.status_code == 200, f"PUT /api/v1/tenders/{tender_id}/rules returned 200 (got {override_res.status_code})")

    override_data = override_res.json()
    assert_test(override_data.get("status") == "success", "Override status is 'success'")
    updated_rules = override_data.get("rules", [])
    assert_test(len(updated_rules) == 3, f"Updated rules count is 3 (got {len(updated_rules)})")

    # Verify updated values in database
    turnover_updated = next((r for r in updated_rules if r.get("metric") == "annual_turnover_cr"), None)
    assert_test(turnover_updated is not None and turnover_updated.get("threshold") == 16.0, "Turnover threshold updated to 16.0 Cr")

    mii_updated = next((r for r in updated_rules if r.get("metric") == "mii_local_content_percentage"), None)
    assert_test(mii_updated is not None and mii_updated.get("threshold") == 60.0, "MII percentage updated to 60.0%")

    audit_hash = override_data.get("audit_event_hash")
    assert_test(bool(audit_hash) and len(audit_hash) == 64, f"Audit event recorded with SHA-256 hash: {audit_hash[:12]}...")


async def main():
    try:
        await connect_to_mongo()
        pdf_bytes = create_sample_tender_pdf()
        test_pdf_parsing_and_table_extraction(pdf_bytes)
        test_rule_extraction_engine(pdf_bytes)
        test_api_endpoints(pdf_bytes)
    finally:
        await close_mongo_connection()

    print(f"\n==========================================")
    print(f"Total assertions: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"==========================================\n")
    if failed > 0:
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
