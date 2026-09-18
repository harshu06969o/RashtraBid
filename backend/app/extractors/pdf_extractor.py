"""
PDF text extraction using PyMuPDF.

Falls back gracefully if PyMuPDF is not available.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger("gemguard.extractor")

UPLOAD_DIR = Path("data/uploads")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
    logger.info("PyMuPDF available (version %s)", fitz.version[0])
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not available — text extraction will be disabled.")


@dataclass
class ExtractionResult:
    """Result of extracting text from a PDF."""
    text: str                     # full concatenated text
    page_count: int
    method: str                   # PYMUPDF | NONE | ERROR
    pages_text: List[str] = field(default_factory=list)   # per-page text
    error: str = ""


def extract_pdf(file_path: str) -> ExtractionResult:
    """
    Extract text from a PDF file using PyMuPDF.
    Returns an ExtractionResult even on failure.
    """
    if not PYMUPDF_AVAILABLE:
        return ExtractionResult(
            text="",
            page_count=0,
            method="NONE",
            error="PyMuPDF is not installed",
        )

    try:
        doc = fitz.open(file_path)
        pages_text: List[str] = []
        for page in doc:
            pages_text.append(page.get_text())
        full_text = "\n\n".join(pages_text)
        page_count = len(doc)
        doc.close()
        logger.info("Extracted %d pages, %d chars from %s", page_count, len(full_text), file_path)
        return ExtractionResult(
            text=full_text,
            page_count=page_count,
            method="PYMUPDF",
            pages_text=pages_text,
        )
    except Exception as exc:
        logger.exception("PDF extraction failed for %s", file_path)
        return ExtractionResult(
            text="",
            page_count=0,
            method="ERROR",
            error=str(exc),
        )


def save_upload(original_filename: str, content: bytes) -> tuple[str, str, str]:
    """
    Save uploaded file bytes to the uploads directory.

    Returns:
        (file_path, safe_filename, md5_hash)
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Safe filename
    safe_name = "".join(
        c if c.isalnum() or c in "._-" else "_"
        for c in original_filename
    )
    file_path = str(UPLOAD_DIR / safe_name)

    file_hash = hashlib.md5(content).hexdigest()

    with open(file_path, "wb") as fh:
        fh.write(content)

    logger.info("Saved upload %s (%d bytes, MD5=%s)", safe_name, len(content), file_hash)
    return file_path, safe_name, file_hash
