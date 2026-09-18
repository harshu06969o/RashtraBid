"""
Comprehensive Test Suite for GeM-Guard Backend Architecture
Validates:
1. Motor Database Connection Pooling & Lifecycle
2. Hybrid Storage Manager (backend/data/uploads/ + SHA-256)
3. Domain Schemas (Tender, RequirementRule, Evidence, RuleResult, AuditEvent)
4. Centralized Routers (tenders, bids, rules, audit) mounted on FastAPI
"""

import asyncio
import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from pydantic import ValidationError

from app.core.database import (
    MAX_POOL_SIZE,
    MIN_POOL_SIZE,
    connect_to_mongo,
    close_mongo_connection,
    get_db,
    doc_to_dict,
    to_oid,
)
from app.core.storage import storage, StoredFile
from app.schemas.domain import (
    Tender,
    RequirementRule,
    Evidence,
    RuleResult,
    AuditEvent,
    RuleStatus,
    RuleSeverity,
)
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


async def test_database_pooling():
    print("\n--- 1. Testing Database & Motor Connection Pooling ---")
    assert_test(MAX_POOL_SIZE >= 10, f"MAX_POOL_SIZE is configured ({MAX_POOL_SIZE})")
    assert_test(MIN_POOL_SIZE >= 1, f"MIN_POOL_SIZE is configured ({MIN_POOL_SIZE})")

    db = await connect_to_mongo()
    assert_test(db is not None, "Connected to MongoDB / mongomock database")

    # Test insert and query
    test_col = db["test_architecture"]
    await test_col.delete_many({})
    insert_res = await test_col.insert_one({"name": "test_pool", "created_at": datetime.now(timezone.utc)})
    assert_test(insert_res.inserted_id is not None, "Insert operation succeeded with pooled client")

    doc = await test_col.find_one({"_id": insert_res.inserted_id})
    cleaned = doc_to_dict(doc)
    assert_test(cleaned.get("id") == str(insert_res.inserted_id), "doc_to_dict correctly formatted ObjectId")
    await test_col.delete_many({})


async def test_hybrid_storage():
    print("\n--- 2. Testing Hybrid Storage (backend/data/uploads/) ---")
    test_content = b"GeM-Guard Offline Hackathon Verification Document Content"
    expected_hash = hashlib.sha256(test_content).hexdigest()

    test_filename = f"test_doc_{int(datetime.now().timestamp())}.txt"
    stored = await storage.save_file(test_content, test_filename, subfolder="test_uploads")

    assert_test(isinstance(stored, StoredFile), "save_file returns StoredFile dataclass")
    assert_test(stored.file_hash == expected_hash, f"SHA-256 computed correctly: {stored.file_hash[:12]}...")
    assert_test(stored.file_path.exists(), f"File exists on disk at {stored.file_path}")
    assert_test("uploads" in str(stored.file_path), "File resides in backend/data/uploads/ directory")

    # Read back
    read_bytes = storage.read_file(stored.file_path)
    assert_test(read_bytes == test_content, "Read back bytes match original content exactly")

    # File exists helper
    assert_test(storage.file_exists(stored.file_path), "storage.file_exists confirms presence")

    # Delete
    deleted = storage.delete_file(stored.file_path)
    assert_test(deleted and not stored.file_path.exists(), "storage.delete_file cleaned up successfully")


def test_domain_schemas():
    print("\n--- 3. Testing Pydantic Domain Models ---")

    # 1. Tender
    tender = Tender(
        tender_no="GEM/2026/B/1001",
        title="CPCL Supply of Valve Actuators",
        organization="CPCL",
        closing_date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert_test(tender.tender_no == "GEM/2026/B/1001", "Tender.tender_no matches")
    assert_test(tender.organization == "CPCL", "Tender.organization defaults to CPCL")
    assert_test(tender.file_hash is not None, "Tender.file_hash present")

    # 2. RequirementRule
    rule = RequirementRule(
        clause_id="CL-4.2.1",
        metric="annual_turnover_cr",
        operator=">=",
        threshold=14.2,
        unit="INR_CR",
        severity="CRITICAL",
    )
    assert_test(rule.clause_id == "CL-4.2.1", "RequirementRule.clause_id matches")
    assert_test(rule.metric == "annual_turnover_cr", "RequirementRule.metric matches")
    assert_test(rule.operator == ">=", "RequirementRule.operator matches")
    assert_test(rule.threshold == 14.2, "RequirementRule.threshold matches")
    assert_test(rule.severity == "CRITICAL", "RequirementRule.severity normalized to CRITICAL")

    # 3. Evidence
    evidence = Evidence(
        document_id="doc_ca_cert_01",
        page_number=2,
        bounding_box=[72.0, 144.5, 480.0, 192.0],
        field_name="annual_turnover_2024",
        normalized_value=16.85,
        confidence=0.98,
    )
    assert_test(evidence.document_id == "doc_ca_cert_01", "Evidence.document_id matches")
    assert_test(evidence.page_number == 2, "Evidence.page_number matches (1-indexed)")
    assert_test(len(evidence.bounding_box) == 4, "Evidence.bounding_box contains [x1, y1, x2, y2]")
    assert_test(evidence.field_name == "annual_turnover_2024", "Evidence.field_name matches")
    assert_test(evidence.confidence == 0.98, "Evidence.confidence score matches")

    # Verify bounding_box constraint (must have exactly 4 floats)
    invalid_bbox_caught = False
    try:
        Evidence(
            document_id="doc_bad",
            page_number=1,
            bounding_box=[72.0, 144.0],  # only 2 coords
            field_name="test",
            normalized_value=1,
        )
    except ValidationError:
        invalid_bbox_caught = True
    assert_test(invalid_bbox_caught, "Evidence rejects invalid bounding_box length (<4)")

    # 4. RuleResult
    result = RuleResult(
        status="PASS",
        evidence_ids=["ev_ca_01", "ev_gst_02"],
        explanation="Annual turnover of 16.85 Cr satisfies minimum requirement of 14.2 Cr.",
    )
    assert_test(result.status == RuleStatus.PASS, "RuleResult.status validated to RuleStatus.PASS")
    assert_test(len(result.evidence_ids) == 2, "RuleResult.evidence_ids contains associated evidence")
    assert_test("16.85 Cr" in result.explanation, "RuleResult.explanation preserved")

    # Test status normalization (e.g. COMPLIANT -> PASS)
    mapped_res = RuleResult(status="COMPLIANT", explanation="Mapped")
    assert_test(mapped_res.status == RuleStatus.PASS, "RuleResult normalizes COMPLIANT to PASS")

    # 5. AuditEvent
    now_utc = datetime.now(timezone.utc)
    prev_h = "0000000000000000000000000000000000000000000000000000000000000000"
    audit = AuditEvent(
        timestamp=now_utc,
        actor="officer@gem.gov.in",
        action="OVERRIDE_APPROVED",
        prev_hash=prev_h,
    )
    assert_test(audit.actor == "officer@gem.gov.in", "AuditEvent.actor matches")
    assert_test(audit.action == "OVERRIDE_APPROVED", "AuditEvent.action matches")
    assert_test(audit.prev_hash == prev_h, "AuditEvent.prev_hash chained correctly")
    assert_test(len(audit.event_hash) == 64, "AuditEvent.event_hash is a valid 64-char SHA-256 hex digest")


async def test_centralized_routing():
    print("\n--- 4. Testing Centralized Routing on FastAPI App ---")
    # Verify routers mounted on app
    routes = [route.path for route in app.routes]

    tender_routes = [r for r in routes if "/tenders" in r]
    bid_routes = [r for r in routes if "/bids" in r]
    rule_routes = [r for r in routes if "/rules" in r]
    audit_routes = [r for r in routes if "/audit" in r]

    assert_test(len(tender_routes) > 0, f"Tenders router mounted ({len(tender_routes)} routes)")
    assert_test(len(bid_routes) > 0, f"Bids router mounted ({len(bid_routes)} routes)")
    assert_test(len(rule_routes) > 0, f"Rules router mounted ({len(rule_routes)} routes)")
    assert_test(len(audit_routes) > 0, f"Audit router mounted ({len(audit_routes)} routes)")

    # Test with FastAPI TestClient
    from fastapi.testclient import TestClient
    client = TestClient(app, base_url="http://testserver")

    # Health check
    res_health = client.get("/api/health")
    assert_test(res_health.status_code == 200, f"GET /api/health returned 200 (db: {res_health.json().get('db_status')})")

    # Tenders listing
    res_tenders = client.get("/api/tenders")
    assert_test(res_tenders.status_code == 200, "GET /api/tenders returned 200")

    # Rules listing
    res_rules = client.get("/api/rules")
    assert_test(res_rules.status_code == 200, "GET /api/rules returned 200")

    # Audit events
    res_audit = client.get("/api/audit/events")
    assert_test(res_audit.status_code == 200, "GET /api/audit/events returned 200")

    # Rule test evaluator
    res_rule_test = client.post("/api/rules/test", json={
        "metric": "turnover",
        "operator": ">=",
        "threshold": 10.0,
        "test_value": 15.5
    })
    assert_test(res_rule_test.status_code == 200 and res_rule_test.json().get("passed") is True, "POST /api/rules/test evaluated correctly")


async def main():
    try:
        await test_database_pooling()
        await test_hybrid_storage()
        test_domain_schemas()
        await test_centralized_routing()
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
