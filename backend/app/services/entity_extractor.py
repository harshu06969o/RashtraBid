"""
Entity Extractor — Stage 3.

Extracts structured fields from bidder document text using deterministic
regex patterns + heuristics.

CRITICAL:
- This module only EXTRACTS values from text.
- It NEVER produces compliance status (PASS / FAIL / REVIEW / PENDING).
- Confidence scores reflect extraction quality only.
- The compliance engine (Stage 4+) uses these values as INPUT, not verdicts.

Supported fields
----------------
TURNOVER          → annual_turnover_avg_3fy
GST_STATUS        → gst_registration_status
ENTITY_NAME       → legal_entity_name (from CA cert / GST cert / letterhead)
UDYAM_STATUS      → udyam_registration_status
CERT_ISSUE_DATE   → certificate_issue_date
CERT_EXPIRY_DATE  → certificate_expiry_date
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("gemguard.extractor.entity")


@dataclass
class ExtractedField:
    """
    A single extracted field from a document.

    confidence: how certain we are we read the text correctly (0.0–1.0).
                NOT a compliance confidence score.
    """
    field: str
    raw_value: str
    normalized_value: Optional[str]
    source_page: Optional[int]
    source_snippet: str
    confidence: float               # extraction confidence only
    extraction_method: str          # PATTERN | DEMO | OCR | MANUAL
    verification_status: str        # UNVERIFIED | REVIEW | MANUAL_REQUIRED


# ── Helpers ────────────────────────────────────────────────────────────────────

_REVIEW_THRESHOLD = 0.6     # confidence below this → REVIEW
_MANUAL_THRESHOLD = 0.3     # confidence below this → MANUAL_REQUIRED


def _status(confidence: float) -> str:
    if confidence >= _REVIEW_THRESHOLD:
        return "UNVERIFIED"
    if confidence >= _MANUAL_THRESHOLD:
        return "REVIEW"
    return "MANUAL_REQUIRED"


def _snippet(text: str, match, context: int = 120) -> str:
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    return text[start:end].replace("\n", " ").strip()


def _page_of(text: str, match_start: int) -> Optional[int]:
    """
    Estimate page number by counting PAGE_BREAK markers.
    PyMuPDF joins pages with form-feed (\\f).
    """
    page = 1
    for ch in text[:match_start]:
        if ch == "\f":
            page += 1
    return page


# ── Pattern definitions ────────────────────────────────────────────────────────

# Turnover — matches e.g. "₹8.7 crore", "Rs. 8.7 Cr", "INR 8.7 crore"
_TURNOVER_RE = re.compile(
    r"(?:average\s+annual\s+turnover|annual\s+turnover|total\s+turnover|turnover)"
    r"[:\s]*(?:of\s+)?(?:rs\.?|inr|\u20b9)?\s*"
    r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:crore|cr\.?|lakh\s+crore)?",
    re.IGNORECASE,
)

# Also match standalone amount formats near "crore"
_AMOUNT_RE = re.compile(
    r"(?:rs\.?|inr|\u20b9)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:crore|cr\.?)",
    re.IGNORECASE,
)

# GST status
_GST_STATUS_RE = re.compile(
    r"(?:gst\s+registration\s+status|registration\s+status)\s*[:\-]?\s*(active|cancelled|suspended|inactive)",
    re.IGNORECASE,
)
_GST_STATUS_LABEL_RE = re.compile(
    r"\bstatus\b\s*[:\-]\s*(active|cancelled|suspended|inactive)",
    re.IGNORECASE,
)

# Udyam status
_UDYAM_STATUS_RE = re.compile(
    r"(?:udyam\s+registration|udyam)\s*[:\-]?\s*(?:status\s*[:\-]?\s*)?(active|valid|expired|cancelled)",
    re.IGNORECASE,
)

# Legal entity name — looks for "Name of the firm:" or "Certified that M/s"
_ENTITY_NAME_RE = re.compile(
    r"(?:name\s+of\s+(?:the\s+)?(?:firm|company|entity|organization)|certified\s+that\s+m/s|this\s+is\s+to\s+certify\s+that)\s*[:\-]?\s*([A-Za-z0-9&/,.\s\-]{4,80})",
    re.IGNORECASE,
)

# Dates — DD/MM/YYYY or DD-MM-YYYY or Month YYYY
_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2}|"
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})\b",
    re.IGNORECASE,
)

_ISSUE_DATE_RE = re.compile(
    r"(?:issue\s+date|issued\s+on|date\s+of\s+issue)\s*[:\-]?\s*"
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})",
    re.IGNORECASE,
)
_EXPIRY_DATE_RE = re.compile(
    r"(?:expiry\s+date|valid\s+(?:till|upto|until|through)|expires?\s+on)\s*[:\-]?\s*"
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})",
    re.IGNORECASE,
)

# GSTIN format
_GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1})\b")

# Udyam number
_UDYAM_NO_RE = re.compile(r"\b(UDYAM-[A-Z]{2}-\d{2}-\d{7})\b", re.IGNORECASE)


# ── Normalisation helpers ──────────────────────────────────────────────────────

def _norm_turnover(raw: str) -> Optional[str]:
    """Normalise turnover to a float string (crore)."""
    digits = raw.replace(",", "").strip()
    try:
        return str(float(digits))
    except ValueError:
        return None


def _norm_status(raw: str) -> str:
    return raw.strip().upper()


def _norm_date(raw: str) -> str:
    return raw.strip()


def _norm_name(raw: str) -> str:
    return " ".join(raw.strip().split())


# ── Main extractor ─────────────────────────────────────────────────────────────

class EntityExtractor:
    """
    Extracts structured fields from plain text extracted from a bidder document.

    Returns a list of ExtractedField objects — one per field found.
    Multiple hits for the same field are included (e.g., multiple dates).
    """

    def extract(self, text: str, doc_type: str = "UNKNOWN") -> List[ExtractedField]:
        results: List[ExtractedField] = []

        results.extend(self._extract_turnover(text))
        results.extend(self._extract_gst_status(text))
        results.extend(self._extract_udyam(text))
        results.extend(self._extract_entity_name(text))
        results.extend(self._extract_dates(text))
        results.extend(self._extract_gstin(text))

        logger.info("Extracted %d fields from doc_type=%s", len(results), doc_type)
        return results

    def _extract_turnover(self, text: str) -> List[ExtractedField]:
        fields = []

        # Try specific turnover pattern first
        for m in _TURNOVER_RE.finditer(text):
            raw = m.group(1)
            norm = _norm_turnover(raw)
            conf = 0.92 if "average annual" in m.group(0).lower() else 0.78
            fields.append(ExtractedField(
                field="turnover_avg_3fy",
                raw_value=m.group(0).strip(),
                normalized_value=norm,
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))

        # Fallback: standalone amount near "crore"
        if not fields:
            for m in _AMOUNT_RE.finditer(text):
                raw = m.group(1)
                norm = _norm_turnover(raw)
                conf = 0.65
                fields.append(ExtractedField(
                    field="turnover_avg_3fy",
                    raw_value=m.group(0).strip(),
                    normalized_value=norm,
                    source_page=_page_of(text, m.start()),
                    source_snippet=_snippet(text, m),
                    confidence=conf,
                    extraction_method="PATTERN",
                    verification_status=_status(conf),
                ))

        # Deduplicate — keep highest confidence per normalised value
        seen = {}
        for f in fields:
            key = f.normalized_value or f.raw_value
            if key not in seen or f.confidence > seen[key].confidence:
                seen[key] = f
        return list(seen.values())

    def _extract_gst_status(self, text: str) -> List[ExtractedField]:
        fields = []
        for pattern, conf_base in [(_GST_STATUS_RE, 0.95), (_GST_STATUS_LABEL_RE, 0.75)]:
            for m in pattern.finditer(text):
                raw = m.group(1)
                norm = _norm_status(raw)
                conf = conf_base
                fields.append(ExtractedField(
                    field="gst_registration_status",
                    raw_value=raw,
                    normalized_value=norm,
                    source_page=_page_of(text, m.start()),
                    source_snippet=_snippet(text, m),
                    confidence=conf,
                    extraction_method="PATTERN",
                    verification_status=_status(conf),
                ))
        # deduplicate by norm value
        seen = {}
        for f in fields:
            key = f.normalized_value or f.raw_value
            if key not in seen or f.confidence > seen[key].confidence:
                seen[key] = f
        return list(seen.values())

    def _extract_udyam(self, text: str) -> List[ExtractedField]:
        fields = []

        # Udyam number
        for m in _UDYAM_NO_RE.finditer(text):
            conf = 0.97
            fields.append(ExtractedField(
                field="udyam_number",
                raw_value=m.group(1).upper(),
                normalized_value=m.group(1).upper(),
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))

        # Udyam status keyword
        for m in _UDYAM_STATUS_RE.finditer(text):
            raw = m.group(1)
            norm = _norm_status(raw)
            conf = 0.88
            fields.append(ExtractedField(
                field="udyam_registration_status",
                raw_value=raw,
                normalized_value=norm,
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))

        return fields

    def _extract_entity_name(self, text: str) -> List[ExtractedField]:
        fields = []
        for m in _ENTITY_NAME_RE.finditer(text):
            raw = m.group(1)
            norm = _norm_name(raw)
            if len(norm) < 4:
                continue
            conf = 0.80
            fields.append(ExtractedField(
                field="legal_entity_name",
                raw_value=raw.strip(),
                normalized_value=norm,
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))
        return fields

    def _extract_dates(self, text: str) -> List[ExtractedField]:
        fields = []

        for m in _ISSUE_DATE_RE.finditer(text):
            raw = m.group(1)
            conf = 0.88
            fields.append(ExtractedField(
                field="certificate_issue_date",
                raw_value=raw,
                normalized_value=_norm_date(raw),
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))

        for m in _EXPIRY_DATE_RE.finditer(text):
            raw = m.group(1)
            conf = 0.88
            fields.append(ExtractedField(
                field="certificate_expiry_date",
                raw_value=raw,
                normalized_value=_norm_date(raw),
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))

        return fields

    def _extract_gstin(self, text: str) -> List[ExtractedField]:
        fields = []
        for m in _GSTIN_RE.finditer(text):
            conf = 0.97
            fields.append(ExtractedField(
                field="gstin",
                raw_value=m.group(1),
                normalized_value=m.group(1).upper(),
                source_page=_page_of(text, m.start()),
                source_snippet=_snippet(text, m),
                confidence=conf,
                extraction_method="PATTERN",
                verification_status=_status(conf),
            ))
        # deduplicate
        seen = {}
        for f in fields:
            if f.normalized_value not in seen:
                seen[f.normalized_value] = f
        return list(seen.values())


# Singleton
entity_extractor = EntityExtractor()
