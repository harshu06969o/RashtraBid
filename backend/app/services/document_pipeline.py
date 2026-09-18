"""
Document Pipeline — Stage 3.

Orchestrates the full processing pipeline for a bidder document:

  1. File validation
  2. PDF text extraction (PyMuPDF + Tesseract fallback)
  3. Document classification (heuristic)
  4. Entity extraction (EntityExtractor)
  5. Evidence creation (BidderEvidence ORM rows)

CRITICAL:
  The pipeline NEVER produces compliance status.
  It produces evidence. The rules engine uses evidence.
  The officer makes the final decision.
"""

import logging
import os
import re
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from pathlib import Path
from app.services.entity_extractor import entity_extractor, ExtractedField
from app.paths import BIDDER_DOCS_DIR

logger = logging.getLogger("gemguard.pipeline")

# Upload directory for bidder documents
UPLOAD_DIR = BIDDER_DOCS_DIR


# ── Document type classifier ───────────────────────────────────────────────────

_DOC_SIGNATURES = {
    "CA_CERTIFICATE": [
        r"chartered\s+accountant",
        r"ca\s+certificate",
        r"annual\s+turnover",
        r"average\s+annual\s+turnover",
        r"certificate\s+of\s+turnover",
        r"profit\s+&\s+loss",
        r"income\s+tax\s+return",
    ],
    "GST_CERTIFICATE": [
        r"goods\s+and\s+services\s+tax",
        r"gst\s+registration",
        r"gstin",
        r"certificate\s+of\s+registration.*gst",
        r"central\s+goods",
    ],
    "UDYAM_CERTIFICATE": [
        r"udyam\s+registration",
        r"udyam\s+certificate",
        r"ministry\s+of\s+msme",
        r"micro\s+small\s+and\s+medium",
        r"udyam-[a-z]{2}-\d{2}-\d{7}",
    ],
    "PAN": [
        r"permanent\s+account\s+number",
        r"\bpan\b.*\bcard\b",
        r"income\s+tax\s+department.*pan",
    ],
}


def classify_document(text: str) -> Tuple[str, float]:
    """
    Classify a document by pattern matching.

    Returns (doc_type, confidence).
    Confidence is classification quality only — not compliance confidence.
    """
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for doc_type, patterns in _DOC_SIGNATURES.items():
        score = 0
        for pat in patterns:
            if re.search(pat, text_lower):
                score += 1
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return "UNKNOWN", 0.4

    best = max(scores, key=scores.get)
    best_score = scores[best]
    total_patterns = len(_DOC_SIGNATURES[best])
    confidence = min(0.95, 0.5 + (best_score / total_patterns) * 0.5)

    return best, round(confidence, 2)


# ── File helpers ───────────────────────────────────────────────────────────────

def _safe_filename(original: str) -> str:
    base = Path(original).name.replace(" ", "_")
    # Remove any non-safe characters
    base = re.sub(r"[^\w.\-]", "", base)
    return base or "document.pdf"


def save_bidder_doc(original_filename: str, content: bytes) -> Tuple[str, str, str]:
    """
    Save uploaded content to disk.
    Returns (file_path, safe_filename, md5_hash).
    """
    import uuid
    safe_name = f"{uuid.uuid4().hex[:8]}_{_safe_filename(original_filename)}"
    file_path = str(UPLOAD_DIR / safe_name)
    with open(file_path, "wb") as f:
        f.write(content)
    md5 = hashlib.md5(content).hexdigest()
    return file_path, safe_name, md5


# ── OCR fallback ───────────────────────────────────────────────────────────────

def _try_tesseract_page(image_bytes: bytes) -> Optional[str]:
    """
    Run Tesseract OCR on raw image bytes.
    Returns extracted text or None if Tesseract unavailable.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang="eng")
    except Exception as exc:
        logger.debug("Tesseract OCR failed: %s", exc)
        return None


def extract_with_fallback(file_path: str) -> dict:
    """
    Extract text from a PDF using PyMuPDF; fall back to Tesseract per page.

    Returns:
        {
            "text": str,
            "page_count": int,
            "method": "PYMUPDF" | "TESSERACT" | "MIXED" | "NONE" | "ERROR",
            "error": str | None,
        }
    """
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # type: ignore
        except ImportError:
            return {"text": "", "page_count": 0, "method": "NONE", "error": "PyMuPDF not installed"}

    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        return {"text": "", "page_count": 0, "method": "ERROR", "error": str(exc)}

    page_texts = []
    methods_used = set()

    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            text = page.get_text("text").strip()

            if text and len(text) > 30:
                page_texts.append(text)
                methods_used.add("PYMUPDF")
            else:
                # Try OCR on this page
                pix = page.get_pixmap(dpi=150)
                ocr_text = _try_tesseract_page(pix.tobytes("png"))
                if ocr_text and len(ocr_text.strip()) > 10:
                    page_texts.append(ocr_text.strip())
                    methods_used.add("TESSERACT")
                else:
                    page_texts.append("")
        except Exception as exc:
            logger.warning("Page %d extraction failed: %s", page_num, exc)
            page_texts.append("")

    doc.close()

    full_text = "\f".join(page_texts)  # \f = form-feed = page separator

    if not methods_used:
        method = "NONE"
    elif len(methods_used) == 1:
        method = methods_used.pop()
    else:
        method = "MIXED"

    return {
        "text": full_text,
        "page_count": len(page_texts),
        "method": method,
        "error": None,
    }


# ── Main pipeline ──────────────────────────────────────────────────────────────

class DocumentPipeline:
    """
    Processes a bidder document through the full pipeline.

    process(db, document_id) → updates Document ORM and creates BidderEvidence rows.
    process_bytes(db, bid_package_id, filename, content) → saves, then process().
    """

    def process_bytes(
        self,
        db,
        bid_package_id: int,
        original_filename: str,
        content: bytes,
    ):
        """
        Full pipeline from raw bytes:
        1. Save file
        2. Extract text
        3. Classify doc
        4. Extract entities
        5. Create BidderEvidence rows

        Returns the Document ORM object.
        """
        from app import models

        # Validate
        if not content:
            raise ValueError("Empty file content")
        if not original_filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported")
        if len(content) > 50 * 1024 * 1024:
            raise ValueError("File exceeds 50 MB limit")

        # Save
        file_path, safe_name, file_hash = save_bidder_doc(original_filename, content)

        # Create Document record (pending)
        doc = models.Document(
            bid_package_id=bid_package_id,
            filename=safe_name,
            original_filename=original_filename,
            file_path=file_path,
            file_hash=file_hash,
            file_size=len(content),
            pipeline_status="PENDING",
        )
        db.add(doc)
        db.flush()

        # Run extraction
        try:
            self._run_pipeline(db, doc)
        except Exception as exc:
            doc.pipeline_status = "FAILED"
            doc.pipeline_error = str(exc)
            logger.error("Pipeline failed for doc %d: %s", doc.id, exc)

        db.commit()
        db.refresh(doc)
        return doc

    def _run_pipeline(self, db, doc) -> None:
        """
        Runs extraction, classification, entity extraction, evidence creation.
        Updates the document record in place.
        """
        from app import models

        # ── Extract text ─────────────────────────────────────────────────────
        extraction = extract_with_fallback(doc.file_path)
        doc.page_count = extraction["page_count"]
        doc.extracted_text = extraction["text"] or None
        doc.extraction_method = extraction["method"]
        doc.extraction_error = extraction["error"]
        db.flush()

        text = extraction["text"] or ""
        if not text.strip():
            doc.pipeline_status = "FAILED"
            doc.pipeline_error = "No text extracted from document"
            return

        # ── Classify ─────────────────────────────────────────────────────────
        doc_type, _cls_confidence = classify_document(text)
        doc.doc_type = doc_type

        # ── Extract entities ──────────────────────────────────────────────────
        fields: List[ExtractedField] = entity_extractor.extract(text, doc_type=doc_type)

        # ── Store raw entities as JSON ────────────────────────────────────────
        doc.extracted_entities = {
            f.field: {
                "raw_value": f.raw_value,
                "normalized_value": f.normalized_value,
                "confidence": f.confidence,
            }
            for f in fields
        }

        # ── Create BidderEvidence rows ────────────────────────────────────────
        for ef in fields:
            ev = models.BidderEvidence(
                document_id=doc.id,
                bid_package_id=doc.bid_package_id,
                field=ef.field,
                raw_value=ef.raw_value,
                normalized_value=ef.normalized_value,
                source_page=ef.source_page,
                source_snippet=ef.source_snippet[:400] if ef.source_snippet else None,
                confidence=round(ef.confidence, 4),
                extraction_method=ef.extraction_method,
                verification_status=ef.verification_status,
            )
            db.add(ev)

        doc.pipeline_status = "PROCESSED"
        doc.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.flush()

        logger.info(
            "Pipeline complete: doc_id=%d, doc_type=%s, fields=%d, method=%s",
            doc.id, doc_type, len(fields), extraction["method"],
        )


# Singleton
document_pipeline = DocumentPipeline()
