"""
GeM-Guard — Vision Intelligence Document Processor Test Suite
Validates:
1. Dual-Engine Extraction (PyMuPDF block/word extraction + 0-1000 normalized coordinates).
2. Entity Classification (CA_CERTIFICATE, GST_CERTIFICATE, PAN_CARD, UDYAM_CERTIFICATE, MII_DECLARATION).
3. Evidence Generation (annual_turnover_cr, local_content_percentage, gstin, pan, udyam_number).
4. MongoDB Evidence persistence with strict schema compliance (page_number, bounding_box, confidence).
5. Multi-file Bid Package processing.
"""

import asyncio
import io
import os
import sys
import unittest
from pathlib import Path

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pymupdf as fitz
from app.core.database import connect_to_mongo, close_mongo_connection, get_db
from app.schemas.domain import Evidence
from app.pipeline.document_processor import (
    normalize_bbox,
    DualEngineExtractor,
    DocumentClassifier,
    EvidenceExtractor,
    BidDocumentProcessor,
    ProcessedPage,
    ExtractedWordOrBlock,
)


def create_mock_pdf(pages_text: list) -> bytes:
    """Helper to generate an in-memory PDF with specified text per page using PyMuPDF."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)  # Standard A4 points
        # Insert text at specific coordinates
        rect = fitz.Rect(50, 80, 545, 750)
        page.insert_textbox(rect, text, fontsize=11, fontname="helv")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestDocumentProcessor(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Connect to mongo (real or mongomock)
        self.db = await connect_to_mongo()

    async def asyncTearDown(self):
        # Cleanup any test artifacts
        if self.db is not None:
            await self.db["evidence"].delete_many({"bid_id": "test_bid_vision_001"})
            await self.db["bid_documents"].delete_many({"bid_id": "test_bid_vision_001"})

    def test_01_coordinate_normalization(self):
        """Test coordinate normalization to 0.0 - 1000.0 scale with bounds and inversion checks."""
        # 1. Normal rect on standard A4 (595 x 842)
        box = normalize_bbox([59.5, 84.2, 297.5, 421.0], 595.0, 842.0)
        self.assertEqual(len(box), 4)
        self.assertAlmostEqual(box[0], 100.0, places=1)
        self.assertAlmostEqual(box[1], 100.0, places=1)
        self.assertAlmostEqual(box[2], 500.0, places=1)
        self.assertAlmostEqual(box[3], 500.0, places=1)

        # 2. Inverted coordinates [x2, y2, x1, y1] -> should auto-sort
        inverted_box = normalize_bbox([300.0, 400.0, 100.0, 200.0], 1000.0, 1000.0)
        self.assertTrue(inverted_box[0] <= inverted_box[2])
        self.assertTrue(inverted_box[1] <= inverted_box[3])
        self.assertEqual(inverted_box, [100.0, 200.0, 300.0, 400.0])

        # 3. Out-of-bounds coordinates -> clamp to 0.0 - 1000.0
        clamped_box = normalize_bbox([-50.0, -20.0, 1200.0, 1500.0], 1000.0, 1000.0)
        self.assertEqual(clamped_box, [0.0, 0.0, 1000.0, 1000.0])
        print("  [PASS] test_01_coordinate_normalization passed.")

    def test_02_dual_engine_pdf_extraction(self):
        """Test PyMuPDF extraction of digital PDF with normalized coordinates."""
        ca_text = (
            "CHARTERED ACCOUNTANT CERTIFICATE\n"
            "This is to certify that M/s BHARAT ENGINEERING LTD\n"
            "Average Annual Turnover for the preceding 3 financial years is Rs. 18.75 Crore.\n"
            "UDIN: 24054321A1B2C3D4E5\n"
            "Date of Issue: 12-08-2024\n"
        )
        pdf_bytes = create_mock_pdf([ca_text])
        pages = DualEngineExtractor.process_pdf(pdf_bytes)

        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page.page_number, 1)
        self.assertFalse(page.is_scanned)
        self.assertIn("18.75 Crore", page.text)
        self.assertTrue(len(page.blocks) > 0)

        # Verify all block bounding boxes are strictly normalized [0.0, 1000.0]
        for blk in page.blocks:
            self.assertEqual(len(blk.bbox), 4)
            for coord in blk.bbox:
                self.assertTrue(0.0 <= coord <= 1000.0, f"Coord {coord} out of range")
        print("  [PASS] test_02_dual_engine_pdf_extraction passed.")

    def test_03_document_classification_all_types(self):
        """Test entity classification across all 5 mandatory document types."""
        samples = [
            (
                "CA_CERTIFICATE",
                "Chartered Accountant Certificate. We certify that the average annual turnover is Rs 25.50 Crore. UDIN 230987654321123456.",
                "CA_Certificate_Turnover.pdf",
            ),
            (
                "GST_CERTIFICATE",
                "Government of India - Form GST REG-06. Registration Certificate. GSTIN: 33AABCT1332L1ZX. Taxpayer Name: BHARAT ENG.",
                "GST_Registration_Certificate.pdf",
            ),
            (
                "PAN_CARD",
                "INCOME TAX DEPARTMENT, GOVT. OF INDIA. Permanent Account Number Card. PAN: AABCT1332L. Name: BHARAT ENGINEERING LTD.",
                "PAN_Card_Copy.pdf",
            ),
            (
                "UDYAM_CERTIFICATE",
                "Ministry of Micro, Small and Medium Enterprises. UDYAM REGISTRATION CERTIFICATE. URN: UDYAM-TN-02-0012345. Enterprise: SMALL.",
                "Udyam_MSME_Certificate.pdf",
            ),
            (
                "MII_DECLARATION",
                "MAKE IN INDIA (PPP-MII) LOCAL CONTENT DECLARATION. We hereby certify that the Local Content is 65.5% as per PPP-MII Order 2017.",
                "Make_In_India_Declaration.pdf",
            ),
        ]

        for expected_type, text, filename in samples:
            doc_type, conf = DocumentClassifier.classify(text, filename=filename)
            self.assertEqual(
                doc_type,
                expected_type,
                f"Expected {expected_type}, got {doc_type} for '{filename}'",
            )
            self.assertTrue(conf >= 0.60, f"Confidence {conf} below threshold for {expected_type}")
        print("  [PASS] test_03_document_classification_all_types passed.")

    def test_04_evidence_extraction_all_key_figures(self):
        """Test extraction of all 5 key figures with exact coordinates and page numbers."""
        # 1. Turnover from CA Cert
        ca_page = ProcessedPage(
            page_number=1,
            text="Chartered Accountant Certificate\nAverage Annual Turnover: Rs. 22.40 Crore\nUDIN: 123456789012345678",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("Average Annual Turnover: Rs. 22.40 Crore", 1, [100.0, 200.0, 500.0, 230.0], 0.98),
            ],
        )
        ca_ev = EvidenceExtractor.extract_evidence("doc_ca", "CA_CERTIFICATE", [ca_page], "bid_1", "bidder_1")
        self.assertEqual(len(ca_ev), 1)
        self.assertEqual(ca_ev[0].field_name, "annual_turnover_cr")
        self.assertEqual(ca_ev[0].normalized_value, 22.40)
        self.assertEqual(ca_ev[0].page_number, 1)
        self.assertEqual(len(ca_ev[0].bounding_box), 4)

        # 2. Local Content from MII Declaration
        mii_page = ProcessedPage(
            page_number=2,
            text="Make In India Declaration\nLocal Content is 58.5% as per DPIIT order.",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("Local Content is 58.5%", 2, [120.0, 350.0, 480.0, 380.0], 0.95),
            ],
        )
        mii_ev = EvidenceExtractor.extract_evidence("doc_mii", "MII_DECLARATION", [mii_page], "bid_1", "bidder_1")
        self.assertEqual(len(mii_ev), 1)
        self.assertEqual(mii_ev[0].field_name, "local_content_percentage")
        self.assertEqual(mii_ev[0].normalized_value, 58.5)
        self.assertEqual(mii_ev[0].page_number, 2)

        # 3. GSTIN from GST Certificate
        gst_page = ProcessedPage(
            page_number=1,
            text="Form GST REG-06\nGSTIN: 27AABCT9999P1Z5\nLegal Name: M/S RELIABLE INFRA",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("GSTIN: 27AABCT9999P1Z5", 1, [80.0, 150.0, 400.0, 180.0], 0.99),
            ],
        )
        gst_ev = EvidenceExtractor.extract_evidence("doc_gst", "GST_CERTIFICATE", [gst_page], "bid_1", "bidder_1")
        self.assertEqual(len(gst_ev), 1)
        self.assertEqual(gst_ev[0].field_name, "gstin")
        self.assertEqual(gst_ev[0].normalized_value, "27AABCT9999P1Z5")

        # 4. PAN from PAN Card
        pan_page = ProcessedPage(
            page_number=1,
            text="INCOME TAX DEPT\nPermanent Account Number: AABCT9999P",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("Permanent Account Number: AABCT9999P", 1, [90.0, 160.0, 350.0, 190.0], 0.99),
            ],
        )
        pan_ev = EvidenceExtractor.extract_evidence("doc_pan", "PAN_CARD", [pan_page], "bid_1", "bidder_1")
        self.assertEqual(len(pan_ev), 1)
        self.assertEqual(pan_ev[0].field_name, "pan")
        self.assertEqual(pan_ev[0].normalized_value, "AABCT9999P")

        # 5. Udyam No. from Udyam Certificate
        udyam_page = ProcessedPage(
            page_number=1,
            text="UDYAM REGISTRATION CERTIFICATE\nUDYAM-MH-01-0098765",
            width=595.0,
            height=842.0,
            blocks=[
                ExtractedWordOrBlock("UDYAM-MH-01-0098765", 1, [100.0, 220.0, 450.0, 250.0], 0.97),
            ],
        )
        udyam_ev = EvidenceExtractor.extract_evidence("doc_udyam", "UDYAM_CERTIFICATE", [udyam_page], "bid_1", "bidder_1")
        self.assertEqual(len(udyam_ev), 1)
        self.assertEqual(udyam_ev[0].field_name, "udyam_number")
        self.assertEqual(udyam_ev[0].normalized_value, "UDYAM-MH-01-0098765")

        print("  [PASS] test_04_evidence_extraction_all_key_figures passed.")

    async def test_05_process_single_file_and_persistence(self):
        """Test processing single document and persisting validated Evidence into MongoDB."""
        bid_id = "test_bid_vision_001"
        ca_pdf = create_mock_pdf([
            "CHARTERED ACCOUNTANTS OF INDIA\n"
            "Certificate of Turnover for M/s TEST BIDDER ENTERPRISE\n"
            "We have verified books of account and certify that Average Annual Turnover is Rs. 16.50 Crore.\n"
            "UDIN: 231234567890123456\n"
        ])

        # Insert doc record in bid_documents first
        doc_rec = {
            "bid_id": bid_id,
            "filename": "ca_turnover_cert.pdf",
            "uploaded_at": "2026-09-11T12:00:00Z",
        }
        res_doc = await self.db["bid_documents"].insert_one(doc_rec)
        doc_id = str(res_doc.inserted_id)

        # Process single file
        result = await BidDocumentProcessor.process_single_file(
            file_path_or_bytes=ca_pdf,
            filename="ca_turnover_cert.pdf",
            document_id=doc_id,
            package_id=bid_id,
            bidder_id="bidder_test_001",
            db=self.db,
        )

        self.assertEqual(result.classified_type, "CA_CERTIFICATE")
        self.assertTrue(result.classification_confidence >= 0.60)
        self.assertTrue(len(result.extracted_evidence) >= 1)

        # Verify Evidence in MongoDB
        saved_ev = await self.db["evidence"].find_one({"bid_id": bid_id, "field_name": "annual_turnover_cr"})
        self.assertIsNotNone(saved_ev, "Evidence was not persisted in MongoDB")
        self.assertEqual(saved_ev["normalized_value"], 16.50)
        self.assertEqual(len(saved_ev["bounding_box"]), 4)
        for c in saved_ev["bounding_box"]:
            self.assertTrue(0.0 <= c <= 1000.0)
        self.assertEqual(saved_ev["page_number"], 1)
        self.assertTrue(saved_ev["confidence"] > 0)
        print("  [PASS] test_05_process_single_file_and_persistence passed.")

    async def test_06_multi_file_bid_package_processing(self):
        """Test processing multi-file bid package with complete evidence synthesis and audit logging."""
        bid_id = "test_bid_vision_001"

        gst_pdf = create_mock_pdf([
            "GOVERNMENT OF INDIA - GST REGISTRATION\n"
            "GSTIN: 07AABCB1234K1ZZ\n"
            "Legal Name: TEST INDUSTRIAL CORP\n"
            "Status: ACTIVE\n"
        ])

        mii_pdf = create_mock_pdf([
            "LOCAL CONTENT DECLARATION (MAKE IN INDIA)\n"
            "We declare that the domestic value addition is 72.0% Local Content.\n"
            "Authorized Signatory\n"
        ])

        files_data = [
            ("gst_certificate.pdf", gst_pdf),
            ("local_content_declaration.pdf", mii_pdf),
        ]

        package_res = await BidDocumentProcessor.process_bid_package(
            bid_id=bid_id,
            files_data=files_data,
            db=self.db,
        )

        self.assertEqual(package_res["processed_documents_count"], 2)
        self.assertTrue(package_res["evidence_count"] >= 2)

        # Check that both GST and MII evidence are in MongoDB
        gst_ev = await self.db["evidence"].find_one({"bid_id": bid_id, "field_name": "gstin"})
        self.assertIsNotNone(gst_ev)
        self.assertEqual(gst_ev["normalized_value"], "07AABCB1234K1ZZ")

        mii_ev = await self.db["evidence"].find_one({"bid_id": bid_id, "field_name": "local_content_percentage"})
        self.assertIsNotNone(mii_ev)
        self.assertEqual(mii_ev["normalized_value"], 72.0)

        # Check audit event logged
        audit_event = await self.db["audit"].find_one({"action": "BID_DOCUMENTS_PROCESSED", "entity_id": bid_id})
        self.assertIsNotNone(audit_event, "Audit event not logged for multi-file package")
        print("  [PASS] test_06_multi_file_bid_package_processing passed.")


def run_tests():
    suite = unittest.TestSuite()
    suite.addTest(TestDocumentProcessor("test_01_coordinate_normalization"))
    suite.addTest(TestDocumentProcessor("test_02_dual_engine_pdf_extraction"))
    suite.addTest(TestDocumentProcessor("test_03_document_classification_all_types"))
    suite.addTest(TestDocumentProcessor("test_04_evidence_extraction_all_key_figures"))
    suite.addTest(TestDocumentProcessor("test_05_process_single_file_and_persistence"))
    suite.addTest(TestDocumentProcessor("test_06_multi_file_bid_package_processing"))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
