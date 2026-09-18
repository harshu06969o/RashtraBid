"""
Test Suite: AI-Powered Bid Document Extraction & Syncing
Validates:
1. Candidate models resolution prioritizing gemini-3.5-flash-lite.
2. Coordinate grounding with _locate_value_in_pages.
3. AI Entity to Evidence conversion with strict schema validation.
4. Pure extraction without dummy mock constants.
5. MongoDB syncing to db["bids"] (extracted_data, documents, bidder_name).
"""

import asyncio
import io
import os
import sys
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pymupdf as fitz
from app.core.database import connect_to_mongo, close_mongo_connection
from app.pipeline.document_processor import (
    BidDocumentProcessor,
    DualEngineExtractor,
    DocumentClassifier,
    EvidenceExtractor,
    GeminiBidDocumentExtractor,
    ProcessedPage,
    ExtractedWordOrBlock,
)


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(50, 80, 545, 750)
    page.insert_textbox(rect, text, fontsize=11, fontname="helv")
    b = doc.tobytes()
    doc.close()
    return b


class TestGeminiBidExtraction(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await connect_to_mongo()

    async def asyncTearDown(self):
        if self.db is not None:
            await self.db["bids"].delete_many({"bid_id": "test_ai_sync_bid"})
            await self.db["bid_documents"].delete_many({"bid_id": "test_ai_sync_bid"})
            await self.db["evidence"].delete_many({"bid_id": "test_ai_sync_bid"})

    def test_01_model_candidate_resolution(self):
        """Ensure gemini-3.5-flash-lite is the first candidate."""
        candidates = GeminiBidDocumentExtractor.resolve_candidate_models()
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0], "gemini-3.5-flash-lite")
        print("  [PASS] test_01_model_candidate_resolution passed.")

    def test_02_coordinate_grounding(self):
        """Test locating exact word coordinates for extracted entities."""
        page = ProcessedPage(
            page_number=1,
            text="Turnover Certificate\nAverage Annual Turnover is Rs. 35.50 Crore\nUDIN: 241234567890123456",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("Turnover Certificate", 1, [100.0, 100.0, 400.0, 120.0], 0.99),
                ExtractedWordOrBlock("Average Annual Turnover is Rs. 35.50 Crore", 1, [100.0, 150.0, 500.0, 175.0], 0.98),
                ExtractedWordOrBlock("UDIN: 241234567890123456", 1, [100.0, 200.0, 450.0, 225.0], 0.99),
            ]
        )
        # Ground turnover
        p_num, bbox, conf = EvidenceExtractor._locate_value_in_pages([page], "35.50 Crore", 35.50)
        self.assertEqual(p_num, 1)
        self.assertEqual(bbox, [100.0, 150.0, 500.0, 175.0])

        # Ground UDIN
        p_num_u, bbox_u, _ = EvidenceExtractor._locate_value_in_pages([page], "241234567890123456", "241234567890123456")
        self.assertEqual(p_num_u, 1)
        self.assertEqual(bbox_u, [100.0, 200.0, 450.0, 225.0])
        print("  [PASS] test_02_coordinate_grounding passed.")

    def test_03_ai_entities_to_evidence_conversion(self):
        """Test converting Gemini AI extracted JSON into validated Evidence domain objects."""
        page = ProcessedPage(
            page_number=1,
            text="GST REG-06 Certificate\nGSTIN: 07AAACA1234A1Z5\nLegal Name: BHARAT HEAVY INFRA LTD",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("GSTIN: 07AAACA1234A1Z5", 1, [80.0, 120.0, 420.0, 145.0], 0.99),
                ExtractedWordOrBlock("Legal Name: BHARAT HEAVY INFRA LTD", 1, [80.0, 160.0, 480.0, 185.0], 0.98),
            ]
        )
        ai_result = {
            "document_type": "GST_CERTIFICATE",
            "classification_confidence": 0.98,
            "legal_name": "BHARAT HEAVY INFRA LTD",
            "entities": [
                {
                    "field_name": "gstin",
                    "normalized_value": "07AAACA1234A1Z5",
                    "raw_value": "07AAACA1234A1Z5",
                    "page_number": 1,
                    "confidence": 0.99,
                },
                {
                    "field_name": "pan",
                    "normalized_value": "AAACA1234A",
                    "raw_value": "AAACA1234A",
                    "page_number": 1,
                    "confidence": 0.98,
                }
            ]
        }
        ev_list = EvidenceExtractor.create_evidence_from_ai_entities(
            document_id="doc_test_123",
            pages=[page],
            ai_result=ai_result,
            package_id="pkg_test_123",
            bidder_id="bidder_test_123",
        )
        self.assertEqual(len(ev_list), 3)  # legal_name + gstin + pan
        field_map = {e.field_name: e for e in ev_list}
        self.assertIn("legal_entity_name", field_map)
        self.assertEqual(field_map["legal_entity_name"].normalized_value, "BHARAT HEAVY INFRA LTD")
        self.assertEqual(field_map["gstin"].normalized_value, "07AAACA1234A1Z5")
        self.assertEqual(field_map["gstin"].bounding_box, [80.0, 120.0, 420.0, 145.0])
        print("  [PASS] test_03_ai_entities_to_evidence_conversion passed.")

    def test_04_no_mock_defaults_when_field_absent(self):
        """Verify that missing figures do not fall back to fake mock numbers like 14.2 or fake GSTINs."""
        random_page = ProcessedPage(
            page_number=1,
            text="Company Brochure\nWe build world-class bridges and roads across India.",
            width=595.0,
            height=842.0,
            blocks=[]
        )
        # CA cert extraction on non-turnover text
        ca_ev = EvidenceExtractor._extract_turnover("d1", [random_page], "p1", "b1")
        self.assertEqual(ca_ev, [], "Expected empty list when turnover is absent, but got fake default!")

        # GST extraction on non-gst text
        gst_ev = EvidenceExtractor._extract_gstin("d2", [random_page], "p1", "b1")
        self.assertEqual(gst_ev, [], "Expected empty list when GSTIN is absent, but got fake default!")
        print("  [PASS] test_04_no_mock_defaults_when_field_absent passed.")

    async def test_05_bid_sync_and_persistence(self):
        """Test that BidDocumentProcessor updates db['bids'] with extracted_data and documents summary."""
        bid_id = "test_ai_sync_bid"

        # Create base bid record
        await self.db["bids"].insert_one({
            "bid_id": bid_id,
            "tender_id": "tender_test_99",
            "bidder_name": "Adani Total Gas Ltd",  # Generic initial name
            "status": "DRAFT",
            "created_at": "2026-09-13T10:00:00Z",
        })

        ca_pdf = make_pdf(
            "CHARTERED ACCOUNTANTS CERTIFICATE\n"
            "M/s HINDUSTAN PRECISION WORKS LTD\n"
            "Average Annual Turnover for the last 3 financial years is Rs. 42.80 Crore.\n"
            "UDIN: 249876543210123456\n"
        )

        # Create bid document record
        doc_rec = {
            "bid_id": bid_id,
            "filename": "ca_cert_hindustan.pdf",
            "uploaded_at": "2026-09-13T10:05:00Z",
        }
        res_doc = await self.db["bid_documents"].insert_one(doc_rec)
        doc_id = str(res_doc.inserted_id)

        # Process single file with document_type_hint
        result = await BidDocumentProcessor.process_single_file(
            file_path_or_bytes=ca_pdf,
            filename="ca_cert_hindustan.pdf",
            document_id=doc_id,
            package_id=bid_id,
            bidder_id=bid_id,
            document_type_hint="CA_CERTIFICATE",
            db=self.db,
        )

        self.assertEqual(result.classified_type, "CA_CERTIFICATE")

        # Verify db["bid_documents"] was updated
        saved_doc = await self.db["bid_documents"].find_one({"_id": res_doc.inserted_id})
        self.assertIsNotNone(saved_doc)
        self.assertEqual(saved_doc["document_type"], "CA_CERTIFICATE")
        self.assertIn("extracted_fields", saved_doc)
        self.assertEqual(saved_doc["extracted_fields"].get("annual_turnover_cr"), 42.80)

        # Verify db["bids"] was updated with extracted_data and document summary!
        updated_bid = await self.db["bids"].find_one({"bid_id": bid_id})
        self.assertIsNotNone(updated_bid)
        self.assertTrue(updated_bid.get("has_documents"))
        self.assertIn("extracted_data", updated_bid)
        self.assertEqual(updated_bid["extracted_data"].get("annual_turnover_cr"), 42.80)
        self.assertTrue(len(updated_bid.get("documents", [])) >= 1)
        self.assertEqual(updated_bid["documents"][0]["filename"], "ca_cert_hindustan.pdf")
        print("  [PASS] test_05_bid_sync_and_persistence passed.")


if __name__ == "__main__":
    unittest.main()
