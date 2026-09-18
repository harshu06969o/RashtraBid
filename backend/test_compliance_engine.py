"""
GeM-Guard — Compliance Engine & Cross-Document Integrity Test Suite
Validates:
1. Deterministic Rule Evaluation: PASS, FAIL, REVIEW, PENDING states.
2. Cross-Document Integrity (Pandas):
   - Legal name contradictions across documents (PAN vs Udyam).
   - Turnover discrepancies (>5% variance) between CA Certificate and Financial Affidavit.
   - Statutory cross-linkage: Embedded PAN inside GSTIN vs Submitted PAN card.
   - Rule state automatically transitions to REVIEW on contradiction.
3. Readiness Score (0-100) & Risk Bands (LOW, MEDIUM, HIGH, CRITICAL).
4. FastAPI Endpoint Integration: POST /api/bids/{bid_id}/evaluate.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import connect_to_mongo, close_mongo_connection
from app.schemas.domain import Evidence, RequirementRule, RuleResult, RuleStatus, RuleSeverity
from app.engine.compliance import (
    ComplianceEngine,
    CrossDocumentValidator,
    IntegrityFinding,
    ComplianceEvaluationReport,
    RiskBand,
)


class TestComplianceEngine(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await connect_to_mongo()
        self.client = TestClient(app)

    async def asyncTearDown(self):
        if self.db is not None:
            await self.db["bids"].delete_many({"bidder_id": "test_bidder_engine_001"})
            await self.db["rules"].delete_many({"tender_id": "test_tender_engine_001"})
            await self.db["evidence"].delete_many({"bid_id": "test_bid_engine_001"})

    def test_01_deterministic_rule_evaluation_states(self):
        """Test deterministic evaluation across operators and states (PASS, FAIL, REVIEW, PENDING)."""
        # Create evidence DataFrame
        df_evidence = pd.DataFrame([
            {"evidence_id": "ev1", "document_id": "d1", "package_id": "b1", "doc_type": "CA_CERTIFICATE", "field_name": "annual_turnover_cr", "normalized_value": 18.5, "raw_value": "18.5 Cr", "confidence": 0.98, "page_number": 1},
            {"evidence_id": "ev2", "document_id": "d2", "package_id": "b1", "doc_type": "MII_DECLARATION", "field_name": "local_content_percentage", "normalized_value": 45.0, "raw_value": "45%", "confidence": 0.95, "page_number": 1},
            {"evidence_id": "ev3", "document_id": "d3", "package_id": "b1", "doc_type": "GST_CERTIFICATE", "field_name": "gst_registration_active", "normalized_value": True, "raw_value": "ACTIVE", "confidence": 0.99, "page_number": 1},
        ])

        # 1. Turnover >= 14.0 -> PASS
        rule_turnover = RequirementRule(
            tender_id="t1",
            clause_id="3.1",
            metric="annual_turnover_cr",
            operator=">=",
            threshold=14.0,
            severity=RuleSeverity.CRITICAL,
        )
        res_turnover = ComplianceEngine.evaluate_rule(rule_turnover, df_evidence, {}, [], "bidder_1")
        self.assertEqual(res_turnover.status, RuleStatus.PASS)
        self.assertIn("18.5 >= required 14.0", res_turnover.explanation)

        # 2. Local content >= 50% (got 45%) -> FAIL
        rule_mii = RequirementRule(
            tender_id="t1",
            clause_id="3.2",
            metric="local_content_percentage",
            operator=">=",
            threshold=50.0,
            severity=RuleSeverity.HIGH,
        )
        res_mii = ComplianceEngine.evaluate_rule(rule_mii, df_evidence, {}, [], "bidder_1")
        self.assertEqual(res_mii.status, RuleStatus.FAIL)
        self.assertIn("45.0", res_mii.explanation)

        # 3. External verification PENDING (simulated timeout) -> PENDING (never FAIL)
        rule_epfo = RequirementRule(
            tender_id="t1",
            clause_id="3.3",
            metric="establishment_code",
            operator="EXISTS",
            threshold="EXISTS",
            verification_source="EPFO",
            severity=RuleSeverity.MEDIUM,
        )
        res_epfo = ComplianceEngine.evaluate_rule(rule_epfo, df_evidence, {"EPFO": "PENDING"}, [], "bidder_1")
        self.assertEqual(res_epfo.status, RuleStatus.PENDING)
        self.assertIn("PENDING", res_epfo.explanation)

        print("  [PASS] test_01_deterministic_rule_evaluation_states passed.")

    def test_02_pandas_legal_name_contradiction(self):
        """Test Pandas cross-document integrity detecting Legal Name contradiction (PAN vs Udyam)."""
        evidence_list = [
            Evidence(
                document_id="doc_pan",
                package_id="bid_1",
                page_number=1,
                bounding_box=[100.0, 100.0, 400.0, 150.0],
                field_name="legal_entity_name",
                normalized_value="BHARAT ENGINEERING PRIVATE LIMITED",
                confidence=0.99,
                doc_type="PAN_CARD",
            ),
            Evidence(
                document_id="doc_udyam",
                package_id="bid_1",
                page_number=1,
                bounding_box=[120.0, 150.0, 450.0, 190.0],
                field_name="legal_entity_name",
                normalized_value="SOUTHERN INFRASTRUCTURE ENTERPRISES LLP",
                confidence=0.98,
                doc_type="UDYAM_CERTIFICATE",
            ),
        ]

        df = CrossDocumentValidator.create_evidence_dataframe(evidence_list)
        findings = CrossDocumentValidator.validate_integrity(df)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.check_type, "NAME_MISMATCH")
        self.assertEqual(finding.severity, "HIGH")
        self.assertIn("PAN_CARD", finding.documents_involved)
        self.assertIn("UDYAM_CERTIFICATE", finding.documents_involved)

        # Rule evaluation for legal entity name MUST be marked as REVIEW
        rule_name = RequirementRule(
            tender_id="t1",
            clause_id="3.5",
            metric="legal_entity_name",
            operator="MATCH",
            threshold="CONSISTENT",
            severity=RuleSeverity.CRITICAL,
        )
        rule_res = ComplianceEngine.evaluate_rule(rule_name, df, {}, findings, "bidder_1")
        self.assertEqual(rule_res.status, RuleStatus.REVIEW)
        self.assertIn("Contradiction flagged by Cross-Document Integrity Engine", rule_res.explanation)
        print("  [PASS] test_02_pandas_legal_name_contradiction passed.")

    def test_03_pandas_turnover_discrepancy(self):
        """Test Pandas cross-document integrity detecting Turnover Discrepancy (>5% variance)."""
        evidence_list = [
            Evidence(
                document_id="doc_ca",
                package_id="bid_1",
                page_number=1,
                bounding_box=[100.0, 100.0, 400.0, 150.0],
                field_name="annual_turnover_cr",
                normalized_value=22.0,  # 22 Crore
                raw_value="Rs. 22.0 Crore",
                confidence=0.99,
                doc_type="CA_CERTIFICATE",
            ),
            Evidence(
                document_id="doc_affidavit",
                package_id="bid_1",
                page_number=1,
                bounding_box=[120.0, 150.0, 450.0, 190.0],
                field_name="annual_turnover_cr",
                normalized_value=15.0,  # 15 Crore -> (22-15)/15 = 46.7% difference (> 5%)
                raw_value="Rs. 15.0 Crore",
                confidence=0.95,
                doc_type="FINANCIAL_AFFIDAVIT",
            ),
        ]

        df = CrossDocumentValidator.create_evidence_dataframe(evidence_list)
        findings = CrossDocumentValidator.validate_integrity(df)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.check_type, "TURNOVER_DISCREPANCY")
        self.assertEqual(finding.severity, "HIGH")
        self.assertIn("46.7%", finding.discrepancy_details)

        # Evaluating the turnover rule MUST be marked as REVIEW due to discrepancy
        rule_turnover = RequirementRule(
            tender_id="t1",
            clause_id="3.1",
            metric="annual_turnover_cr",
            operator=">=",
            threshold=14.0,
            severity=RuleSeverity.CRITICAL,
        )
        rule_res = ComplianceEngine.evaluate_rule(rule_turnover, df, {}, findings, "bidder_1")
        self.assertEqual(rule_res.status, RuleStatus.REVIEW)
        self.assertIn("Contradiction flagged", rule_res.explanation)
        print("  [PASS] test_03_pandas_turnover_discrepancy passed.")

    def test_04_pandas_pan_gstin_cross_linkage(self):
        """Test statutory cross-linkage: Embedded PAN inside GSTIN vs submitted PAN Card."""
        evidence_list = [
            Evidence(
                document_id="doc_gst",
                package_id="bid_1",
                page_number=1,
                bounding_box=[100.0, 100.0, 400.0, 150.0],
                field_name="gstin",
                normalized_value="33AABCT1332L1ZX",  # Embedded PAN is AABCT1332L
                confidence=0.99,
                doc_type="GST_CERTIFICATE",
            ),
            Evidence(
                document_id="doc_pan",
                package_id="bid_1",
                page_number=1,
                bounding_box=[120.0, 150.0, 450.0, 190.0],
                field_name="pan",
                normalized_value="BBBCP9999K",  # Discrepant PAN
                confidence=0.99,
                doc_type="PAN_CARD",
            ),
        ]

        df = CrossDocumentValidator.create_evidence_dataframe(evidence_list)
        findings = CrossDocumentValidator.validate_integrity(df)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.check_type, "PAN_GSTIN_MISMATCH")
        self.assertEqual(finding.severity, "CRITICAL")
        self.assertEqual(finding.values_found["embedded_pan"], "AABCT1332L")
        self.assertEqual(finding.values_found["submitted_pan"], "BBBCP9999K")
        print("  [PASS] test_04_pandas_pan_gstin_cross_linkage passed.")

    def test_05_readiness_score_and_risk_bands(self):
        """Test Readiness Score (0-100) and mapping across all 4 Risk Bands (LOW, MEDIUM, HIGH, CRITICAL)."""
        rules = [
            RequirementRule(tender_id="t1", metric="annual_turnover_cr", operator=">=", threshold=14.0, severity=RuleSeverity.CRITICAL),
            RequirementRule(tender_id="t1", metric="local_content_percentage", operator=">=", threshold=50.0, severity=RuleSeverity.HIGH),
            RequirementRule(tender_id="t1", metric="gst_registration_active", operator="==", threshold=True, severity=RuleSeverity.CRITICAL),
        ]

        # 1. Clean compliant bid -> LOW Risk (Score >= 80)
        clean_ev = [
            Evidence(document_id="d1", page_number=1, bounding_box=[0, 0, 10, 10], field_name="annual_turnover_cr", normalized_value=18.0),
            Evidence(document_id="d2", page_number=1, bounding_box=[0, 0, 10, 10], field_name="local_content_percentage", normalized_value=65.0),
            Evidence(document_id="d3", page_number=1, bounding_box=[0, 0, 10, 10], field_name="gst_registration_active", normalized_value=True),
        ]
        rep_clean = ComplianceEngine.evaluate_bid("bid_clean", rules, clean_ev, [{"source": "GSTN", "status": "VERIFIED"}])
        self.assertEqual(rep_clean.risk_band, RiskBand.LOW)
        self.assertTrue(rep_clean.readiness_score >= 80.0)
        self.assertEqual(rep_clean.overall_status, "COMPLIANT")

        # 2. Minor discrepancy bid -> MEDIUM Risk
        findings_med = [IntegrityFinding("NAME_MISMATCH", "MEDIUM", "name", ["D1", "D2"], "Minor punctuation variance", {})]
        score_med, band_med, status_med, _, _ = ComplianceEngine.calculate_readiness_and_risk(
            [
                RuleResult(rule_id="r1", status=RuleStatus.PASS, explanation="Pass"),
                RuleResult(rule_id="r2", status=RuleStatus.REVIEW, explanation="Review"),
                RuleResult(rule_id="r3", status=RuleStatus.PASS, explanation="Pass"),
            ],
            findings_med,
            rules,
        )
        self.assertEqual(band_med, RiskBand.MEDIUM)
        self.assertTrue(60.0 <= score_med <= 79.9)

        # 3. High contradiction bid -> HIGH Risk
        findings_high = [IntegrityFinding("TURNOVER_DISCREPANCY", "HIGH", "annual_turnover_cr", ["CA", "AFF"], "Turnover variance 35%", {})]
        score_high, band_high, status_high, _, _ = ComplianceEngine.calculate_readiness_and_risk(
            [
                RuleResult(rule_id="r1", status=RuleStatus.REVIEW, explanation="Review"),
                RuleResult(rule_id="r2", status=RuleStatus.PASS, explanation="Pass"),
                RuleResult(rule_id="r3", status=RuleStatus.PASS, explanation="Pass"),
            ],
            findings_high,
            rules,
        )
        self.assertEqual(band_high, RiskBand.HIGH)

        # 4. Mandatory Failure / Critical Contradiction -> CRITICAL Risk
        fail_ev = [
            Evidence(document_id="d1", page_number=1, bounding_box=[0, 0, 10, 10], field_name="annual_turnover_cr", normalized_value=6.0),  # Under threshold
            Evidence(document_id="d2", page_number=1, bounding_box=[0, 0, 10, 10], field_name="local_content_percentage", normalized_value=25.0),
        ]
        rep_crit = ComplianceEngine.evaluate_bid("bid_crit", rules, fail_ev, [{"source": "DEBARMENT", "status": "MISMATCH"}])
        self.assertEqual(rep_crit.risk_band, RiskBand.CRITICAL)
        self.assertEqual(rep_crit.overall_status, "NON_COMPLIANT")
        self.assertTrue(rep_crit.readiness_score < 40.0)

        print("  [PASS] test_05_readiness_score_and_risk_bands passed.")

    async def test_06_fastapi_evaluate_bid_integration(self):
        """Test POST /api/bids/{bid_id}/evaluate with Compliance Engine integration."""
        tender_id = "test_tender_engine_001"
        await self.db["rules"].insert_many([
            {
                "tender_id": tender_id,
                "metric": "annual_turnover_cr",
                "operator": ">=",
                "threshold": 12.0,
                "severity": "CRITICAL",
            },
            {
                "tender_id": tender_id,
                "metric": "local_content_percentage",
                "operator": ">=",
                "threshold": 50.0,
                "severity": "HIGH",
            },
        ])

        # Create Bid
        res_bid = await self.db["bids"].insert_one({
            "tender_id": tender_id,
            "bidder_id": "test_bidder_engine_001",
            "bidder_name": "Engine Test Enterprise",
            "status": "SUBMITTED",
            "created_at": "2026-09-11T12:00:00Z",
        })
        bid_id = str(res_bid.inserted_id)

        # Seed Evidence with Turnover and Local Content
        await self.db["evidence"].insert_many([
            {
                "bid_id": bid_id,
                "package_id": bid_id,
                "document_id": "doc_1",
                "page_number": 1,
                "bounding_box": [100.0, 100.0, 400.0, 150.0],
                "field_name": "annual_turnover_cr",
                "normalized_value": 16.0,
                "confidence": 0.98,
                "doc_type": "CA_CERTIFICATE",
            },
            {
                "bid_id": bid_id,
                "package_id": bid_id,
                "document_id": "doc_2",
                "page_number": 1,
                "bounding_box": [120.0, 150.0, 450.0, 190.0],
                "field_name": "local_content_percentage",
                "normalized_value": 62.0,
                "confidence": 0.95,
                "doc_type": "MII_DECLARATION",
            },
        ])

        # Call evaluate endpoint
        eval_resp = self.client.post(f"/api/bids/{bid_id}/evaluate")
        self.assertEqual(eval_resp.status_code, 200)
        data = eval_resp.json()

        self.assertEqual(data["bid_id"], bid_id)
        self.assertEqual(data["overall_status"], "COMPLIANT")
        self.assertEqual(data["risk_band"], "LOW")
        self.assertTrue(data["readiness_score"] >= 80.0)
        self.assertEqual(len(data["results"]), 2)
        for r in data["results"]:
            self.assertEqual(r["status"], "PASS")

        # Confirm persisted in MongoDB
        updated_bid = await self.db["bids"].find_one({"_id": res_bid.inserted_id})
        self.assertEqual(updated_bid["compliance_status"], "COMPLIANT")
        self.assertEqual(updated_bid["risk_band"], "LOW")
        self.assertEqual(updated_bid["readiness_score"], data["readiness_score"])

        print("  [PASS] test_06_fastapi_evaluate_bid_integration passed.")


def run_tests():
    suite = unittest.TestSuite()
    suite.addTest(TestComplianceEngine("test_01_deterministic_rule_evaluation_states"))
    suite.addTest(TestComplianceEngine("test_02_pandas_legal_name_contradiction"))
    suite.addTest(TestComplianceEngine("test_03_pandas_turnover_discrepancy"))
    suite.addTest(TestComplianceEngine("test_04_pandas_pan_gstin_cross_linkage"))
    suite.addTest(TestComplianceEngine("test_05_readiness_score_and_risk_bands"))
    suite.addTest(TestComplianceEngine("test_06_fastapi_evaluate_bid_integration"))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
