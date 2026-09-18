"""
GeM-Guard — Cryptographic Audit Trail, Officer Override & Corrigendum Test Suite
Validates:
1. Cryptographic Audit Trail: Chained SHA-256 (event_hash = SHA256(prev_hash + payload)),
   append-only logging, and tamper detection.
2. Officer Override (POST /api/v1/bids/{id}/override):
   - Mandatory justification enforcement (rejects empty/whitespace with 400).
   - Rule outcome alteration, risk score recalculation, and cryptographic log chaining.
3. Corrigendum Impact Analyzer (POST /api/v1/tenders/{id}/corrigendum):
   - Re-evaluates strictly the changed rule against existing evidence.
   - Outputs impact diff summary (flipped statuses, delta metrics).
   - Historical corrigenda listing.
"""

import asyncio
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import connect_to_mongo, close_mongo_connection
from app.engine.audit import AuditEngine, canonical_json
from app.schemas.domain import RequirementRule, Evidence, RuleStatus, RuleSeverity


class TestAuditAndCorrigendum(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await connect_to_mongo()
        self.client = TestClient(app)

    async def asyncTearDown(self):
        if self.db is not None:
            await self.db["audit"].delete_many({"actor": "test_security_officer"})
            await self.db["audit"].delete_many({"entity_id": "test_bid_sec_001"})
            await self.db["audit"].delete_many({"entity_id": "test_tender_sec_001"})
            await self.db["bids"].delete_many({"tender_id": "test_tender_sec_001"})
            await self.db["rules"].delete_many({"tender_id": "test_tender_sec_001"})
            await self.db["tenders"].delete_many({"tender_no": "GEM/2026/B/TEST-SEC-01"})
            await self.db["corrigenda"].delete_many({"tender_id": "test_tender_sec_001"})

    async def test_01_cryptographic_audit_trail_chaining(self):
        """Test append-only chained SHA-256 calculation (event_hash = SHA256(prev_hash + payload))."""
        # Append 3 sequential events
        ev1 = await AuditEngine.append_event(
            db=self.db,
            action="AI_EXTRACTION_COMPLETED",
            actor="test_security_officer",
            entity_id="test_bid_sec_001",
            details={"pages_extracted": 3, "confidence": 0.98},
            event_type="AI_EXTRACTION",
        )

        ev2 = await AuditEngine.append_event(
            db=self.db,
            action="GOV_VERIFICATION_RECORDED",
            actor="test_security_officer",
            entity_id="test_bid_sec_001",
            details={"connector": "GSTN", "status": "VERIFIED"},
            event_type="VERIFICATION",
        )

        ev3 = await AuditEngine.append_event(
            db=self.db,
            action="OFFICER_OVERRIDE",
            actor="test_security_officer",
            entity_id="test_bid_sec_001",
            details={"justification": "Verified physical certificate with bank"},
            event_type="OFFICER_ACTION",
        )

        # Assert chaining: ev2.prev_hash == ev1.event_hash
        self.assertEqual(ev2["prev_hash"], ev1["event_hash"])
        self.assertEqual(ev3["prev_hash"], ev2["event_hash"])

        # Manually re-verify ev3 hash calculation
        ev3_payload = {
            "action": "OFFICER_OVERRIDE",
            "actor": "test_security_officer",
            "details": {"justification": "Verified physical certificate with bank"},
            "entity_id": "test_bid_sec_001",
            "event_type": "OFFICER_ACTION",
            "timestamp": ev3["timestamp"],
        }
        manual_hash = hashlib.sha256(
            f"{ev2['event_hash']}{canonical_json(ev3_payload)}".encode("utf-8")
        ).hexdigest()
        self.assertEqual(ev3["event_hash"], manual_hash)

        # Cryptographic chain verification
        chain_status = await AuditEngine.verify_chain(self.db)
        self.assertTrue(chain_status["valid"])
        self.assertEqual(chain_status["status"], "VERIFIED")
        print("  [PASS] test_01_cryptographic_audit_trail_chaining passed.")

    async def test_02_audit_chain_tamper_detection(self):
        """Test tamper detection when an adversary alters an event payload in MongoDB."""
        # Insert initial clean event
        ev = await AuditEngine.append_event(
            db=self.db,
            action="INITIAL_STATE",
            actor="test_security_officer",
            entity_id="test_bid_sec_001",
            details={"risk": "LOW"},
        )
        ev_id = ev["_id"]

        # Adversary alters details in the database directly
        from bson import ObjectId
        await self.db["audit"].update_one(
            {"_id": ObjectId(ev_id)},
            {"$set": {"details.risk": "TAMPERED_CRITICAL"}},
        )

        # Verify chain detection
        verification = await AuditEngine.verify_chain(self.db)
        self.assertFalse(verification["valid"])
        self.assertEqual(verification["status"], "TAMPERED")
        self.assertIn("tampered", verification["reason"].lower())

        # Cleanup tampered event so subsequent tests pass
        await self.db["audit"].delete_one({"_id": ObjectId(ev_id)})
        print("  [PASS] test_02_audit_chain_tamper_detection passed.")

    async def test_03_officer_override_mandatory_justification(self):
        """Test POST /api/v1/bids/{id}/override strictly rejects missing/empty justification with 400."""
        # Create test bid
        res_bid = await self.db["bids"].insert_one({
            "tender_id": "test_tender_sec_001",
            "bidder_id": "test_bidder_sec_001",
            "compliance_status": "NON_COMPLIANT",
            "risk_score": 85.0,
            "created_at": "2026-09-11T12:00:00Z",
        })
        bid_id = str(res_bid.inserted_id)

        # 1. Reject empty justification
        resp_empty = self.client.post(
            f"/api/v1/bids/{bid_id}/override",
            json={"justification": "   ", "new_status": "PASS"},
        )
        self.assertEqual(resp_empty.status_code, 400)
        self.assertIn("justification is mandatory", resp_empty.json()["detail"])

        # 2. Reject short/unsubstantiated justification (<5 chars)
        resp_short = self.client.post(
            f"/api/v1/bids/{bid_id}/override",
            json={"justification": "ok", "new_status": "PASS"},
        )
        self.assertEqual(resp_short.status_code, 400)

        # 3. Reject invalid status
        resp_bad_status = self.client.post(
            f"/api/v1/bids/{bid_id}/override",
            json={"justification": "Valid justification but bad status", "new_status": "SUPER_PASS"},
        )
        self.assertEqual(resp_bad_status.status_code, 400)

        print("  [PASS] test_03_officer_override_mandatory_justification passed.")

    async def test_04_officer_override_success_and_audit_logging(self):
        """Test successful Officer Override alters rule state, recalculates risk, and logs to hash chain."""
        # Create test bid with failing turnover rule
        res_bid = await self.db["bids"].insert_one({
            "tender_id": "test_tender_sec_001",
            "bidder_id": "test_bidder_sec_001",
            "compliance_status": "NON_COMPLIANT",
            "risk_score": 85.0,
            "evaluation_results": [
                {
                    "rule_id": "RULE-TURN-001",
                    "metric": "annual_turnover_cr",
                    "status": "FAIL",
                    "explanation": "Turnover 11.5 Cr < 14.2 Cr required.",
                }
            ],
            "created_at": "2026-09-11T12:00:00Z",
        })
        bid_id = str(res_bid.inserted_id)

        justification_text = "Relaxation granted by Competent Authority under MSME Startup Policy waiver approval ref CPCL/FIN/2026/89."
        resp_override = self.client.post(
            f"/api/v1/bids/{bid_id}/override",
            json={
                "rule_id": "RULE-TURN-001",
                "metric": "annual_turnover_cr",
                "new_status": "PASS",
                "justification": justification_text,
                "actor": "officer@gem.gov.in",
            },
        )
        self.assertEqual(resp_override.status_code, 200)
        data = resp_override.json()

        # Check response details
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["previous_status"], "FAIL")
        self.assertEqual(data["overridden_status"], "PASS")
        self.assertEqual(data["new_compliance_status"], "COMPLIANT")
        self.assertEqual(data["new_risk_score"], 15.0)
        self.assertEqual(len(data["event_hash"]), 64)

        # Check database update
        updated_bid = await self.db["bids"].find_one({"_id": res_bid.inserted_id})
        self.assertEqual(updated_bid["compliance_status"], "COMPLIANT")
        self.assertTrue(updated_bid["officer_override_active"])
        self.assertEqual(updated_bid["latest_override"]["justification"], justification_text)

        # Confirm cryptographic audit event logged
        audit_ev = await self.db["audit"].find_one({"event_hash": data["event_hash"]})
        self.assertIsNotNone(audit_ev)
        self.assertEqual(audit_ev["action"], "OFFICER_OVERRIDE")
        self.assertEqual(audit_ev["details"]["justification"], justification_text)

        print("  [PASS] test_04_officer_override_success_and_audit_logging passed.")

    async def test_05_corrigendum_impact_analyzer_flips_eligibility(self):
        """
        Test Corrigendum Analyzer:
        Accepts mid-process rule amendment, re-evaluates strictly the changed rule,
        and outputs impact diff summary (FAIL -> PASS flip).
        """
        # 1. Create Tender in DB
        res_tender = await self.db["tenders"].insert_one({
            "tender_no": "GEM/2026/B/TEST-SEC-01",
            "title": "Supply of High Pressure Control Valves",
            "organization": "CPCL",
            "status": "ACTIVE",
            "created_at": "2026-09-11T12:00:00Z",
        })
        tender_id = str(res_tender.inserted_id)

        # 2. Create Initial Rule: Turnover >= 14.2 Cr
        res_rule = await self.db["rules"].insert_one({
            "tender_id": tender_id,
            "clause_id": "3.1",
            "metric": "annual_turnover_cr",
            "operator": ">=",
            "threshold": 14.2,
            "unit": "INR_CR",
            "severity": "CRITICAL",
        })

        # 3. Create Bidder A with Turnover = 12.0 Cr (FAIL under 14.2 Cr threshold)
        res_bid_a = await self.db["bids"].insert_one({
            "tender_id": tender_id,
            "bidder_id": "bidder_alpha",
            "bidder_name": "Alpha Engineering Works",
            "compliance_status": "NON_COMPLIANT",
            "risk_score": 85.0,
            "evaluation_results": [
                {
                    "rule_id": str(res_rule.inserted_id),
                    "metric": "annual_turnover_cr",
                    "status": "FAIL",
                    "explanation": "Turnover 12.0 Cr < 14.2 Cr.",
                }
            ],
            "created_at": "2026-09-11T12:00:00Z",
        })
        bid_a_id = str(res_bid_a.inserted_id)

        # Seed Evidence for Bidder A
        await self.db["evidence"].insert_one({
            "bid_id": bid_a_id,
            "package_id": bid_a_id,
            "document_id": "doc_ca_alpha",
            "page_number": 1,
            "bounding_box": [100.0, 100.0, 400.0, 150.0],
            "field_name": "annual_turnover_cr",
            "normalized_value": 12.0,  # Exactly 12.0 Cr
            "confidence": 0.99,
            "doc_type": "CA_CERTIFICATE",
        })

        # 4. Create Bidder B with Turnover = 18.0 Cr (already PASS under 14.2 Cr)
        res_bid_b = await self.db["bids"].insert_one({
            "tender_id": tender_id,
            "bidder_id": "bidder_beta",
            "bidder_name": "Beta Heavy Industries Ltd",
            "compliance_status": "COMPLIANT",
            "risk_score": 15.0,
            "evaluation_results": [
                {
                    "rule_id": str(res_rule.inserted_id),
                    "metric": "annual_turnover_cr",
                    "status": "PASS",
                    "explanation": "Turnover 18.0 Cr >= 14.2 Cr.",
                }
            ],
            "created_at": "2026-09-11T12:00:00Z",
        })
        bid_b_id = str(res_bid_b.inserted_id)

        # Seed Evidence for Bidder B
        await self.db["evidence"].insert_one({
            "bid_id": bid_b_id,
            "package_id": bid_b_id,
            "document_id": "doc_ca_beta",
            "page_number": 1,
            "bounding_box": [100.0, 100.0, 400.0, 150.0],
            "field_name": "annual_turnover_cr",
            "normalized_value": 18.0,
            "confidence": 0.99,
            "doc_type": "CA_CERTIFICATE",
        })

        # 5. Issue Corrigendum: Relax Turnover Threshold to 10.0 Cr
        corr_resp = self.client.post(
            f"/api/v1/tenders/{tender_id}/corrigendum",
            json={
                "corrigendum_number": "CORR-2026-01",
                "metric": "annual_turnover_cr",
                "new_threshold": 10.0,
                "operator": ">=",
                "reason": "Relaxation of financial turnover criteria following Pre-Bid Conference representation",
                "actor": "officer@gem.gov.in",
                "apply_changes": True,
            },
        )
        self.assertEqual(corr_resp.status_code, 200)
        corr_data = corr_resp.json()

        # Assert Impact Diff Summary
        self.assertEqual(corr_data["status"], "success")
        self.assertEqual(corr_data["bids_evaluated_count"], 2)
        self.assertEqual(corr_data["impacted_bids_count"], 1)  # Only Bidder A flipped
        self.assertEqual(corr_data["flips_to_pass_count"], 1)
        self.assertEqual(corr_data["flips_to_fail_count"], 0)
        self.assertEqual(len(corr_data["event_hash"]), 64)

        # Check flipped bid details
        flips = corr_data["status_flips"]
        self.assertEqual(len(flips), 1)
        self.assertEqual(flips[0]["bid_id"], bid_a_id)
        self.assertEqual(flips[0]["previous_status"], "FAIL")
        self.assertEqual(flips[0]["new_status"], "PASS")
        self.assertIn("ELIGIBILITY_GAINED", flips[0]["delta_impact"])

        # Confirm Bidder A is now COMPLIANT in DB
        updated_a = await self.db["bids"].find_one({"_id": res_bid_a.inserted_id})
        self.assertEqual(updated_a["compliance_status"], "COMPLIANT")
        self.assertEqual(updated_a["risk_score"], 15.0)

        # Confirm Rule updated in DB
        updated_rule = await self.db["rules"].find_one({"_id": res_rule.inserted_id})
        self.assertEqual(updated_rule["threshold"], 10.0)
        self.assertEqual(updated_rule["last_corrigendum"], "CORR-2026-01")

        # Confirm listing historical corrigenda
        list_resp = self.client.get(f"/api/v1/tenders/{tender_id}/corrigenda")
        self.assertEqual(list_resp.status_code, 200)
        corr_history = list_resp.json()
        self.assertEqual(len(corr_history), 1)
        self.assertEqual(corr_history[0]["corrigendum_number"], "CORR-2026-01")

        print("  [PASS] test_05_corrigendum_impact_analyzer_flips_eligibility passed.")


def run_tests():
    suite = unittest.TestSuite()
    suite.addTest(TestAuditAndCorrigendum("test_01_cryptographic_audit_trail_chaining"))
    suite.addTest(TestAuditAndCorrigendum("test_02_audit_chain_tamper_detection"))
    suite.addTest(TestAuditAndCorrigendum("test_03_officer_override_mandatory_justification"))
    suite.addTest(TestAuditAndCorrigendum("test_04_officer_override_success_and_audit_logging"))
    suite.addTest(TestAuditAndCorrigendum("test_05_corrigendum_impact_analyzer_flips_eligibility"))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
