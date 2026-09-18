"""
GeM-Guard — Government Connectors & Graceful Degradation Test Suite
Validates:
1. Base Adapter contract: source, status, timestamp, and raw_hash (SHA-256).
2. All 6 Mock Adapters: GSTN, PAN, Udyam, EPFO, Startup India, and Debarment registries.
3. Graceful Degradation (SIH USP): simulate_timeout produces status PENDING.
4. Compliance Engine Rule: External API timeouts NEVER auto-disqualify (fail) a bid.
5. End-to-End router integration via FastAPI TestClient.
"""

import asyncio
import hashlib
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
from app.schemas.domain import RuleStatus
from app.connectors.base import (
    BaseConnector,
    ConnectorResult,
    ConnectorStatus,
    compute_sha256,
)
from app.connectors.gstn import GSTNConnector
from app.connectors.pan import PANConnector
from app.connectors.udyam import UdyamConnector
from app.connectors.epfo import EPFOConnector
from app.connectors.startup_india import StartupIndiaConnector
from app.connectors.debarment import DebarmentConnector
from app.connectors.manager import ConnectorManager, connector_manager


class TestGovernmentConnectors(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await connect_to_mongo()
        self.client = TestClient(app)

    async def asyncTearDown(self):
        if self.db is not None:
            await self.db["bids"].delete_many({"bidder_id": "test_bidder_connector_001"})
            await self.db["rules"].delete_many({"tender_id": "test_tender_conn_001"})
            await self.db["audit"].delete_many({"entity_id": "test_bidder_connector_001"})

    def test_01_base_adapter_contract(self):
        """Test base adapter contract: source, status, timestamp, and raw_hash."""
        raw_payload = {"test": 123, "entity": "Bharat Engineering"}
        expected_hash = hashlib.sha256('{"entity": "Bharat Engineering", "test": 123}'.encode()).hexdigest()
        self.assertEqual(compute_sha256(raw_payload), expected_hash)

        # Verify ConnectorResult validation
        result = ConnectorResult(
            source="GSTN",
            status=ConnectorStatus.VERIFIED,
            raw_hash=expected_hash,
            data={"test": 123},
            message="Verified",
        )
        self.assertEqual(result.source, "GSTN")
        self.assertEqual(result.status, "VERIFIED")
        self.assertEqual(result.raw_hash, expected_hash)
        self.assertTrue(len(result.timestamp) > 0)
        self.assertEqual(len(result.raw_hash), 64)
        print("  [PASS] test_01_base_adapter_contract passed.")

    async def test_02_all_six_mock_adapters_verified(self):
        """Test standard VERIFIED paths across all 6 mock adapters."""
        query = {
            "legal_name": "Bharat Engineering Ltd",
            "bidder_name": "Bharat Engineering Ltd",
            "gstin": "33AABCT1332L1ZX",
            "pan": "AABCT1332L",
            "udyam_number": "UDYAM-TN-02-0012345",
            "epfo_establishment_code": "TN/MAS/0098765/000",
            "dipp_number": "DIPP102345",
            "is_startup": True,
        }

        # 1. GSTN
        gst_res = await GSTNConnector().verify(query)
        self.assertEqual(gst_res.source, "GSTN")
        self.assertEqual(gst_res.status, ConnectorStatus.VERIFIED)
        self.assertEqual(len(gst_res.raw_hash), 64)
        self.assertEqual(gst_res.data["registration_status"], "ACTIVE")

        # 2. PAN
        pan_res = await PANConnector().verify(query)
        self.assertEqual(pan_res.source, "PAN")
        self.assertEqual(pan_res.status, ConnectorStatus.VERIFIED)
        self.assertEqual(len(pan_res.raw_hash), 64)
        self.assertEqual(pan_res.data["pan_status"], "ACTIVE")

        # 3. UDYAM
        udyam_res = await UdyamConnector().verify(query)
        self.assertEqual(udyam_res.source, "UDYAM")
        self.assertEqual(udyam_res.status, ConnectorStatus.VERIFIED)
        self.assertEqual(len(udyam_res.raw_hash), 64)
        self.assertEqual(udyam_res.data["enterprise_type"], "SMALL")

        # 4. EPFO
        epfo_res = await EPFOConnector().verify(query)
        self.assertEqual(epfo_res.source, "EPFO")
        self.assertEqual(epfo_res.status, ConnectorStatus.VERIFIED)
        self.assertEqual(len(epfo_res.raw_hash), 64)
        self.assertEqual(epfo_res.data["compliance_status"], "COMPLIANT")

        # 5. STARTUP_INDIA
        startup_res = await StartupIndiaConnector().verify(query)
        self.assertEqual(startup_res.source, "STARTUP_INDIA")
        self.assertEqual(startup_res.status, ConnectorStatus.VERIFIED)
        self.assertEqual(len(startup_res.raw_hash), 64)
        self.assertTrue(startup_res.data["turnover_relaxation_eligible"])

        # 6. DEBARMENT
        debar_res = await DebarmentConnector().verify(query)
        self.assertEqual(debar_res.source, "DEBARMENT")
        self.assertEqual(debar_res.status, ConnectorStatus.VERIFIED)
        self.assertEqual(len(debar_res.raw_hash), 64)
        self.assertFalse(debar_res.data["debarred"])

        print("  [PASS] test_02_all_six_mock_adapters_verified passed.")

    async def test_03_mock_adapters_discrepancies(self):
        """Test MISMATCH and NOT_FOUND behaviors (cancelled GSTIN, debarred entity)."""
        # Cancelled GSTIN
        bad_gst_res = await GSTNConnector().verify({"gstin": "29ABCDE1234F1Z5"})
        self.assertEqual(bad_gst_res.status, ConnectorStatus.MISMATCH)
        self.assertIn("CANCELLED", bad_gst_res.message)

        # Debarred bidder
        debar_bad_res = await DebarmentConnector().verify({
            "pan": "BADDD1234F",
            "legal_name": "FRAUDULENT SUPPLIERS PVT LTD",
        })
        self.assertEqual(debar_bad_res.status, ConnectorStatus.MISMATCH)
        self.assertTrue(debar_bad_res.data["debarred"])
        self.assertIn("CRITICAL", debar_bad_res.message)

        # Missing identifiers
        missing_gst = await GSTNConnector().verify({})
        self.assertEqual(missing_gst.status, ConnectorStatus.NOT_FOUND)

        missing_pan = await PANConnector().verify({})
        self.assertEqual(missing_pan.status, ConnectorStatus.NOT_FOUND)

        print("  [PASS] test_03_mock_adapters_discrepancies passed.")

    async def test_04_graceful_degradation_timeout_toggle(self):
        """
        Test simulate_timeout toggle (SIH USP):
        When active, adapter MUST output status PENDING with valid raw_hash.
        """
        manager = ConnectorManager()
        query = {"gstin": "33AABCT1332L1ZX", "pan": "AABCT1332L"}

        # 1. Global simulate_timeout=True
        results = await manager.verify_all(query=query, simulate_timeout=True)
        self.assertEqual(len(results), 6)
        for r in results:
            self.assertEqual(
                r.status,
                ConnectorStatus.PENDING,
                f"Connector {r.source} failed to output PENDING on simulate_timeout=True",
            )
            self.assertTrue(r.is_timeout)
            self.assertEqual(len(r.raw_hash), 64)
            self.assertIn("PENDING", r.message)

        # 2. Granular timeout on specific connectors: GSTN & EPFO only
        partial_results = await manager.verify_all(
            query=query,
            simulate_timeout=False,
            timeout_connectors=["GSTN", "EPFO"],
        )
        res_map = {r.source: r for r in partial_results}
        self.assertEqual(res_map["GSTN"].status, ConnectorStatus.PENDING)
        self.assertEqual(res_map["EPFO"].status, ConnectorStatus.PENDING)
        self.assertEqual(res_map["PAN"].status, ConnectorStatus.VERIFIED)
        self.assertEqual(res_map["DEBARMENT"].status, ConnectorStatus.VERIFIED)

        # 3. Impact evaluation
        impact = manager.evaluate_connector_impact(results)
        self.assertEqual(impact["pending_count"], 6)
        self.assertEqual(impact["overall_recommendation"], "HOLD_PENDING")
        self.assertFalse(impact["auto_disqualified"])
        self.assertTrue(impact["graceful_degradation_active"])

        print("  [PASS] test_04_graceful_degradation_timeout_toggle passed.")

    async def test_05_compliance_engine_never_disqualifies_on_timeout(self):
        """
        CRITICAL TEST (SIH USP):
        Verify that when a government API times out (status: PENDING),
        the compliance engine sets the rule to PENDING and NEVER auto-disqualifies (fails) the bid.
        """
        tender_id = "test_tender_conn_001"
        # Seed statutory rules requiring GST and PAN
        await self.db["rules"].insert_many([
            {
                "tender_id": tender_id,
                "metric": "gst_registration_active",
                "operator": "==",
                "threshold": True,
                "verification_source": "GSTN",
                "severity": "CRITICAL",
            },
            {
                "tender_id": tender_id,
                "metric": "pan_card_valid",
                "operator": "==",
                "threshold": True,
                "verification_source": "PAN",
                "severity": "CRITICAL",
            },
        ])

        # Create a bid with TIMED OUT (PENDING) GSTN verification
        bid_doc = {
            "tender_id": tender_id,
            "bidder_id": "test_bidder_connector_001",
            "bidder_name": "Dynamic Infra Ltd",
            "status": "SUBMITTED",
            "verifications": [
                {
                    "source": "GSTN",
                    "status": "PENDING",  # Timed out!
                    "is_timeout": True,
                    "raw_hash": compute_sha256("timeout_gstn"),
                    "timestamp": "2026-09-11T12:00:00Z",
                },
                {
                    "source": "PAN",
                    "status": "VERIFIED",
                    "is_timeout": False,
                    "raw_hash": compute_sha256("verified_pan"),
                    "timestamp": "2026-09-11T12:00:00Z",
                },
            ],
            "created_at": "2026-09-11T12:00:00Z",
        }
        res_bid = await self.db["bids"].insert_one(bid_doc)
        bid_id = str(res_bid.inserted_id)

        # Call evaluate_bid endpoint
        eval_resp = self.client.post(f"/api/bids/{bid_id}/evaluate")
        self.assertEqual(eval_resp.status_code, 200)
        eval_data = eval_resp.json()

        # Check compliance results
        results = eval_data["results"]
        self.assertEqual(len(results), 2)

        # GSTN rule MUST be PENDING, NOT FAIL
        gst_rule_res = [r for r in results if "GSTN" in r["explanation"]][0]
        self.assertEqual(
            gst_rule_res["status"],
            RuleStatus.PENDING.value,
            f"Rule status was '{gst_rule_res['status']}' instead of PENDING on API timeout!",
        )
        self.assertIn("Per SIH Graceful Degradation guarantee", gst_rule_res["explanation"])

        # Overall status MUST NOT be NON_COMPLIANT
        self.assertNotEqual(eval_data["overall_status"], "NON_COMPLIANT")
        self.assertEqual(eval_data["overall_status"], "PENDING_VERIFICATION")
        self.assertTrue(eval_data["risk_score"] < 50.0)

        print("  [PASS] test_05_compliance_engine_never_disqualifies_on_timeout passed.")

    async def test_06_verify_endpoint_with_simulate_timeout(self):
        """Test POST /api/bids/{bid_id}/verify endpoint with simulate_timeout=True."""
        # Create test bid
        res_bid = await self.db["bids"].insert_one({
            "tender_id": "test_tender_conn_001",
            "bidder_id": "test_bidder_connector_001",
            "bidder_name": "Hindustan Engineering Works",
            "bidder_category": "SMALL",
            "created_at": "2026-09-11T12:00:00Z",
        })
        bid_id = str(res_bid.inserted_id)

        # Trigger verification with simulate_timeout=True
        verify_resp = self.client.post(
            f"/api/bids/{bid_id}/verify",
            json={"simulate_timeout": True},
        )
        self.assertEqual(verify_resp.status_code, 200)
        resp_data = verify_resp.json()

        self.assertEqual(resp_data["bid_id"], bid_id)
        verifs = resp_data["verifications"]
        self.assertEqual(len(verifs), 6)

        # All 6 must be PENDING with SHA-256 hash
        for v in verifs:
            self.assertEqual(v["status"], ConnectorStatus.PENDING.value)
            self.assertTrue(v["is_timeout"])
            self.assertEqual(len(v["raw_hash"]), 64)

        # Verify impact metadata
        impact = resp_data["impact"]
        self.assertTrue(impact["has_timeouts"])
        self.assertFalse(impact["auto_disqualified"])
        self.assertTrue(impact["graceful_degradation_active"])
        self.assertEqual(impact["pending_count"], 6)

        print("  [PASS] test_06_verify_endpoint_with_simulate_timeout passed.")


def run_tests():
    suite = unittest.TestSuite()
    suite.addTest(TestGovernmentConnectors("test_01_base_adapter_contract"))
    suite.addTest(TestGovernmentConnectors("test_02_all_six_mock_adapters_verified"))
    suite.addTest(TestGovernmentConnectors("test_03_mock_adapters_discrepancies"))
    suite.addTest(TestGovernmentConnectors("test_04_graceful_degradation_timeout_toggle"))
    suite.addTest(TestGovernmentConnectors("test_05_compliance_engine_never_disqualifies_on_timeout"))
    suite.addTest(TestGovernmentConnectors("test_06_verify_endpoint_with_simulate_timeout"))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
