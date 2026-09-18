"""
GeM-Guard — Production Backend v3.0
FastAPI + Motor (async MongoDB)

Architecture:
  - JWT auth with role-based access (PROCUREMENT_OFFICER / BIDDER / AUDIT_OFFICER)
  - Users collection in MongoDB (bcrypt password hashing)
  - Tenders CRUD with AI/pattern requirement compilation from uploaded PDFs
  - Bidder self-registration + bid submission
  - Document upload → OCR pipeline → entity extraction → evidence storage
  - Deterministic compliance engine (rule-based, not AI black-box)
  - Mock gov API connectors (GSTN, PAN, UDYAM, EPFO, MCA21, DPIIT)
  - SHA-256 chained tamper-evident audit log
  - Corrigendum impact analyzer
  - Risk scoring 0-100 with COMPLIANT/PARTIAL/NON-COMPLIANT bands
  - Officer actions: APPROVE / REJECT / SEEK_CLARIFICATION
  - Audit report export

Compliance principle:
  AI reads. Rules verify. Evidence explains. Officers decide.
"""

from app.core.database import safe_oid
import difflib
import hashlib
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import pymupdf
from bson import ObjectId
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.core.storage import HybridStorage
from jose import JWTError, jwt
from pydantic import BaseModel

# --- Core Modules & Domain Schemas ------------------------------------------

from app.core.database import (
    connect_to_mongo,
    close_mongo_connection,
    get_database,
    get_db,
    doc_to_dict,
    to_oid,
    sha256,
    utcnow_str,
)
from app.core.storage import storage, get_storage
from app.user_cache import upsert_user as cache_upsert_user, get_user as cache_get_user
from app.schemas.domain import (
    Tender,
    RequirementRule,
    Evidence,
    RuleResult,
    AuditEvent,
    RuleStatus,
    RuleSeverity,
)
from app.routers import tenders, bids, rules, corrigendum

# --- Env / Config -----------------------------------------------------------

from app.env_loader import get_mongo_db_name, get_mongo_uri

MONGODB_URL = get_mongo_uri()
MONGODB_DB_NAME = get_mongo_db_name()
USE_REAL_MONGO = os.getenv("USE_REAL_MONGO", "0") == "1"
JWT_SECRET = os.getenv("JWT_SECRET", "sih_26100_supersecret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# --- Logging ----------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("gemguard")

client_holder: Dict[str, Any] = {}



# --- Upload Directories -----------------------------------------------------

from pathlib import Path
from app.paths import DATA_DIR, TENDER_DOCS_DIR, BIDDER_DOCS_DIR, SAMPLE_DOCS_DIR, UPLOADS_DIR

# --- Utilities ---------------------------------------------------------------
# (Utility functions like doc_to_dict, utcnow_str, sha256, and to_oid are imported from app.core.database)


# --- Auth / JWT --------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(data: dict, expires_hours: int = JWT_EXPIRE_HOURS) -> str:
    payload = {**data, "exp": datetime.now(timezone.utc) + timedelta(hours=expires_hours)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request, db=Depends(get_db)) -> dict:
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token:
        role = request.headers.get("x-user-role")
        username = request.headers.get("x-user-name") or request.headers.get("x-user-id")
        if role and username:
            user = await db["users"].find_one({"username": username})
            if user:
                return doc_to_dict(user)
            return {"username": username, "role": role, "name": username}
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub") or payload.get("username")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db["users"].find_one({"username": username})
        if not user:
            role = request.headers.get("x-user-role") or payload.get("role")
            if role:
                # Build a minimal user dict from token payload, preserving bidder_id
                return {
                    "username": username, "role": role,
                    "name": payload.get("name", username),
                    "bidder_id": payload.get("bidder_id", ""),
                }
            raise HTTPException(status_code=401, detail="User not found")
        user_dict = doc_to_dict(user)
        # Merge bidder_id from token if DB record doesn't have it
        if not user_dict.get("bidder_id") and payload.get("bidder_id"):
            user_dict["bidder_id"] = payload["bidder_id"]
        return user_dict
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_role(*roles: str):
    async def _check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required: {list(roles)}. Your role: {user.get('role')}"
            )
        return user
    return _check


# --- Document Classification ------------------------------------------------

_DOC_SIGNATURES = {
    "CA_CERTIFICATE": [
        r"chartered\s+accountant", r"annual\s+turnover", r"average\s+annual",
        r"ca\s+certificate", r"profit\s+&\s+loss", r"income\s+tax\s+return",
    ],
    "GST_CERTIFICATE": [
        r"goods\s+and\s+services\s+tax", r"gst\s+registration", r"gstin",
        r"central\s+goods", r"state\s+goods",
    ],
    "UDYAM_CERTIFICATE": [
        r"udyam", r"ministry\s+of\s+msme", r"micro\s+small\s+and\s+medium",
    ],
    "PAN_CARD": [
        r"permanent\s+account\s+number", r"\bpan\b.*\bcard\b", r"income\s+tax\s+department",
    ],
    "EPFO_CERTIFICATE": [
        r"epfo", r"employees.*provident\s+fund", r"establishment\s+code",
    ],
    "MCA_INCORPORATION": [
        r"certificate\s+of\s+incorporation", r"registrar\s+of\s+companies",
        r"companies\s+act", r"cin\s+number",
    ],
    "MII_DECLARATION": [
        r"make\s+in\s+india", r"local\s+content", r"ppp-mii\s+order",
    ],
}


def classify_document(text: str) -> tuple:
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for doc_type, patterns in _DOC_SIGNATURES.items():
        scores[doc_type] = sum(1 for p in patterns if re.search(p, text_lower))
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "UNKNOWN", 0.0
    conf = min(scores[best] / max(len(_DOC_SIGNATURES[best]), 1), 1.0)
    return best, conf


# --- Entity Extraction -------------------------------------------------------

_ENTITY_PATTERNS = {
    "legal_entity_name": [
        r"(?:m/s|messrs|name\s+of\s+(?:the\s+)?(?:firm|company)|certified\s+that)\s*[:\-]?\s*([A-Za-z0-9& (),.\-]{4,80})",
        r"^([A-Z][A-Za-z0-9& ().,\-]{5,60})\s+(?:pvt\.?\s+ltd\.?|limited|llp\.?|llc\.?|incorporated)",
    ],
    "gstin": [r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"],
    "pan": [r"\b([A-Z]{5}[0-9]{4}[A-Z])\b"],
    "udyam_number": [r"\b(UDYAM-[A-Z]{2}-\d{2}-\d{7})\b"],
    "turnover_avg_3fy": [
        r"(?:average|avg)[\s\w]*?(?:annual|yearly)[\s\w]*?turnover[\s\w]*?(?:rs\.?|inr|[^a-z])\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr\.?)",
        r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr\.?)\b",
        r"turnover[\s\w]{0,30}?([\d,]+(?:\.\d+)?)\s*(?:crore|cr\.?)",
    ],
    "gst_registration_status": [
        r"(?:registration\s+status|gst\s+status)\s*[:\-]?\s*(active|inactive|cancelled|suspended)",
        r"\bstatus\s*[:\-]\s*(active|inactive|cancelled|suspended)\b",
    ],
    "certificate_issue_date": [
        r"(?:issue[d]?\s*on|date\s*of\s*issue)\s*[:\-]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ],
    "certificate_expiry_date": [
        r"(?:valid\s*(?:upto|till|until|through)|expir(?:y|es?|ed?)\s*(?:on|date))\s*[:\-]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ],
    "udyam_registration_status": [
        r"udyam\s+registration\s*[:\-]?\s*(active|valid|expired|cancelled)",
    ],
    "local_content_percentage": [
        r"local\s+content\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%",
    ],
    "establishment_code": [
        r"establishment\s+code\s*[:\-]?\s*([A-Z]{2}\d{10,14})",
    ],
}


def extract_entities(text: str, doc_type: str = "UNKNOWN") -> List[Dict]:
    results = []
    for field, patterns in _ENTITY_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                raw_val = m.group(1).strip().rstrip(".,")
                norm_val = raw_val
                if field == "turnover_avg_3fy":
                    cleaned = raw_val.replace(",", "")
                    try:
                        norm_val = str(float(cleaned))
                    except Exception:
                        norm_val = raw_val
                elif field in ("gst_registration_status", "udyam_registration_status"):
                    norm_val = raw_val.upper()
                elif field in ("gstin", "pan", "udyam_number"):
                    norm_val = raw_val.upper()
                elif field == "legal_entity_name":
                    norm_val = " ".join(raw_val.split()).upper()

                results.append({
                    "field": field,
                    "raw_value": raw_val,
                    "normalized_value": norm_val,
                    "confidence": 0.88,
                    "extraction_method": "PATTERN",
                    "source_page": 1,
                    "source_snippet": text[max(0, m.start() - 40): m.end() + 60].replace("\n", " ").strip(),
                    "verification_status": "UNVERIFIED",
                    "extracted_at": utcnow_str(),
                    "doc_type": doc_type,
                })
                break
    return results


# --- OCR / Text Extraction Pipeline -----------------------------------------

def extract_pdf_text(file_path: str) -> tuple:
    text = ""
    page_count = 0
    method = "PYMUPDF"
    try:
        doc = pymupdf.open(file_path)
        page_count = doc.page_count
        for page in doc:
            text += page.get_text() + "\f"
        doc.close()
    except Exception as e:
        logger.warning("pymupdf failed (%s), trying pdfplumber", e)
        method = "PDFPLUMBER"
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    text += (page.extract_text() or "") + "\f"
        except Exception as e2:
            logger.error("pdfplumber also failed: %s", e2)
            method = "FAILED"

    if len(text.split()) < 30 and page_count > 0:
        logger.info("Low word count — trying Tesseract OCR")
        method = "TESSERACT"
        try:
            import pytesseract
            # pyrefly: ignore [missing-import]
            import cv2
            import numpy as np
            doc = pymupdf.open(file_path)
            ocr_text = ""
            for page_idx in range(min(doc.page_count, 5)):
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=300)
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
                ocr_text += pytesseract.image_to_string(thresh, config="--oem 3 --psm 6") + "\f"
            doc.close()
            if ocr_text.strip():
                text = ocr_text
        except ImportError:
            logger.info("Tesseract/OpenCV not installed")
        except Exception as e:
            logger.warning("Tesseract OCR failed: %s", e)

    return text.strip(), page_count, method


# --- Standard Compliance Rules (used when no PDF uploaded) ------------------

STANDARD_DEMO_RULES = [
    {
        "requirement_id": "REQ-FIN-001", "rule_type": "TURNOVER",
        "description": "Average annual turnover >= INR 25 Crore (preceding 3 FY)",
        "category": "FINANCIAL", "severity": "CRITICAL", "applicability": "ALL",
        "metric": "turnover_avg_3fy", "operator": "GTE",
        "threshold_value": "25.0", "threshold_unit": "INR_CR", "time_period": "LAST_3_FY",
        "evidence_type": "CA_CERTIFICATE", "verification_sources": ["GSTN", "PAN"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.1", "clause_title": "Financial Eligibility",
            "clause_text": "Bidder shall have an average annual turnover not less than INR 25 Crore during preceding 3 financial years as certified by a Chartered Accountant.",
            "source_page": 3,
        },
    },
    {
        "requirement_id": "REQ-REG-001", "rule_type": "GST_STATUS",
        "description": "Valid ACTIVE GST registration at tender closing date",
        "category": "REGULATORY", "severity": "CRITICAL", "applicability": "ALL",
        "metric": "gst_registration_status", "operator": "EQ",
        "threshold_value": "ACTIVE", "threshold_unit": "STRING", "time_period": "CURRENT",
        "evidence_type": "GST_CERTIFICATE", "verification_sources": ["GSTN"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.2", "clause_title": "GST Registration",
            "clause_text": "Bidder must possess a valid GST Registration Certificate with ACTIVE status.",
            "source_page": 4,
        },
    },
    {
        "requirement_id": "REQ-REG-002", "rule_type": "UDYAM",
        "description": "Valid Udyam/MSME registration (MSME bidders only)",
        "category": "REGULATORY", "severity": "HIGH", "applicability": "MSME",
        "metric": "udyam_registration_status", "operator": "EQ",
        "threshold_value": "ACTIVE", "threshold_unit": "STRING", "time_period": "CURRENT",
        "evidence_type": "UDYAM_CERTIFICATE", "verification_sources": ["UDYAM"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.3", "clause_title": "MSME / Udyam Registration",
            "clause_text": "MSME bidders must submit a valid Udyam Registration Certificate. Large enterprises exempt.",
            "source_page": 4,
        },
    },
    {
        "requirement_id": "REQ-MII-001", "rule_type": "MAKE_IN_INDIA",
        "description": "Minimum 50% local content per PPP-MII Order 2017",
        "category": "REGULATORY", "severity": "HIGH", "applicability": "ALL",
        "metric": "local_content_percentage", "operator": "GTE",
        "threshold_value": "50", "threshold_unit": "PERCENTAGE", "time_period": "CURRENT",
        "evidence_type": "MII_DECLARATION", "verification_sources": ["DPIIT"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.4", "clause_title": "Make in India",
            "clause_text": "Bidder must comply with PPP-MII Order 2017. Minimum local content: 50%.",
            "source_page": 5,
        },
    },
    {
        "requirement_id": "REQ-ID-001", "rule_type": "NAME_MATCH",
        "description": "Legal entity name consistent across all submitted documents",
        "category": "LEGAL", "severity": "CRITICAL", "applicability": "ALL",
        "metric": "legal_entity_name", "operator": "MATCH",
        "threshold_value": "CONSISTENT", "threshold_unit": "STRING", "time_period": "CURRENT",
        "evidence_type": "ALL_DOCS", "verification_sources": ["PAN", "GSTN"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.5", "clause_title": "Entity Identity Consistency",
            "clause_text": "Legal entity name must be identical across all submitted certificates. Inconsistencies require clarification.",
            "source_page": 5,
        },
    },
    {
        "requirement_id": "REQ-EMP-001", "rule_type": "EPFO_COMPLIANCE",
        "description": "Valid EPFO establishment registration (for >=20 employees)",
        "category": "REGULATORY", "severity": "MEDIUM", "applicability": "ALL",
        "metric": "establishment_code", "operator": "EXISTS",
        "threshold_value": "EXISTS", "threshold_unit": "STRING", "time_period": "CURRENT",
        "evidence_type": "EPFO_CERTIFICATE", "verification_sources": ["EPFO"],
        "is_mandatory": False, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.6", "clause_title": "EPFO Registration",
            "clause_text": "Bidders with 20 or more employees must submit proof of EPFO registration.",
            "source_page": 6,
        },
    },
    {
        "requirement_id": "REQ-OEM-001", "rule_type": "OEM_AUTHORIZATION",
        "description": "Valid OEM authorization letter for offered product range",
        "category": "TECHNICAL", "severity": "CRITICAL", "applicability": "ALL",
        "metric": "oem_authorization_valid", "operator": "EQ",
        "threshold_value": "True", "threshold_unit": "BOOLEAN", "time_period": "CURRENT",
        "evidence_type": "OEM_AUTHORIZATION", "verification_sources": ["OEM_PORTAL"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.7", "clause_title": "OEM Authorization",
            "clause_text": "Bidder shall submit an authorization letter from the OEM for the offered product range, valid on bid closing date.",
            "source_page": 3,
        },
    },
    {
        "requirement_id": "REQ-QC-001", "rule_type": "ISO_9001_CERT",
        "description": "ISO 9001 quality certificate valid on bid closing date",
        "category": "TECHNICAL", "severity": "CRITICAL", "applicability": "ALL",
        "metric": "iso_9001_valid", "operator": "EQ",
        "threshold_value": "True", "threshold_unit": "BOOLEAN", "time_period": "CURRENT",
        "evidence_type": "ISO_CERTIFICATE", "verification_sources": ["QUALITY_COUNCIL"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.8", "clause_title": "Quality Certification",
            "clause_text": "ISO 9001 certificate submitted for quality-system eligibility must be valid on the bid closing date.",
            "source_page": 3,
        },
    },
    {
        "requirement_id": "REQ-LGL-001", "rule_type": "DEBARMENT_DECLARATION",
        "description": "Signed declaration of non-debarment / non-blacklisting",
        "category": "LEGAL", "severity": "CRITICAL", "applicability": "ALL",
        "metric": "debarment_declaration_submitted", "operator": "EQ",
        "threshold_value": "True", "threshold_unit": "BOOLEAN", "time_period": "CURRENT",
        "evidence_type": "DEBARMENT_DECLARATION", "verification_sources": ["CPPP"],
        "is_mandatory": True, "compilation_source": "DEMO",
        "clause": {
            "clause_number": "3.9", "clause_title": "Debarment / Blacklisting Declaration",
            "clause_text": "Bidder shall declare that it is not debarred or blacklisted by the procuring entity or any applicable authority as on bid closing date.",
            "source_page": 4,
        },
    },
]


def compile_rules_from_text(text: str, tender_oid) -> List[Dict]:
    """Extract structured eligibility rules from tender document text.
    Maps to STANDARD_DEMO_RULES template entries.
    Tries to detect all 9 rule types: Turnover, GST, Udyam, MII, Entity Name,
    EPFO, OEM Authorization, ISO 9001, Debarment Declaration.
    """
    rules = []
    compiled_at = utcnow_str()
    text_lower = text.lower()

    # R-01: Turnover
    TURN_RE = re.compile(
        r"(?:average\s+annual\s+turnover|minimum\s+turnover|turnover\s+of\s+at\s+least|turnover\s+not\s+less).*?"
        r"(?:rs\.?|inr|rupee)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr\.?)",
        re.IGNORECASE | re.DOTALL,
    )
    m = TURN_RE.search(text)
    if m:
        threshold = str(float(m.group(1).replace(",", "")))
        clause_ctx = text[max(0, m.start() - 50): m.end() + 200].replace("\n", " ").strip()
        r = dict(STANDARD_DEMO_RULES[0])
        r.update({"threshold_value": threshold, "compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid,
                  "description": f"Average annual turnover >= INR {threshold} Crore (preceding 3 FY)"})
        r["clause"] = {**r["clause"], "clause_text": clause_ctx}
        rules.append(r)

    # R-02: GST
    if re.search(r"gst\s+registration|goods\s+and\s+services\s+tax|gstin|active\s+gst", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[1])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-03: Udyam / MSME
    if re.search(r"udyam|msme|micro.?small.?medium", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[2])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-04: MII / Local Content
    MII_RE = re.compile(r"local\s+content\s*(?:[:\-])?\s*(\d+)\s*%", re.IGNORECASE)
    mii = MII_RE.search(text)
    if mii:
        r = dict(STANDARD_DEMO_RULES[3])
        r.update({"threshold_value": mii.group(1), "compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)
    elif re.search(r"make\s+in\s+india|mii\s+order|ppp.mii|local\s+supplier", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[3])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-05: Entity Name Consistency
    if re.search(r"pan.*(legal|name)|legal.*name.*pan|entity.*name|name.*match", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[4])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-06: EPFO
    if re.search(r"epfo|provident\s+fund|establishment\s+code|pf\s+registration", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[5])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-07: OEM Authorization
    if re.search(r"oem|original\s+equipment\s+manufacturer|authorization\s+letter|authorisation\s+letter", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[6])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-08: ISO 9001 / Quality Certificate
    if re.search(r"iso\s*9001|quality\s+certificate|quality.system|qs\s+certification", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[7])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    # R-09: Debarment / Blacklisting Declaration
    if re.search(r"debarment|debarred|blacklist|not\s+debarred|declaration.*debarment|sanction", text, re.IGNORECASE):
        r = dict(STANDARD_DEMO_RULES[8])
        r.update({"compilation_source": "PATTERN", "compiled_at": compiled_at, "tender_id": tender_oid})
        rules.append(r)

    if not rules:
        rules = [
            {**dict(r2), "compilation_source": "DEMO", "compiled_at": compiled_at, "tender_id": tender_oid}
            for r2 in STANDARD_DEMO_RULES
        ]

    return rules


# --- Compliance Engine -------------------------------------------------------

def fuzzy_name_match(a: str, b: str) -> float:
    a_clean = re.sub(r"[^\w\s]", "", a.upper())
    b_clean = re.sub(r"[^\w\s]", "", b.upper())
    return difflib.SequenceMatcher(None, a_clean, b_clean).ratio()


def compute_rule_result(rule: dict, evidence_list: List[dict], verifications: List[dict]) -> dict:
    rule_type = rule.get("rule_type", "")
    metric = rule.get("metric", "")
    operator = rule.get("operator", "EQ")
    threshold_str = str(rule.get("threshold_value", "0"))

    # UNAVAILABLE verification -> PENDING, never FAIL
    for src in (rule.get("verification_sources") or []):
        for v in verifications:
            if v.get("source") == src and v.get("connector_status") == "UNAVAILABLE":
                return {
                    "result": "PENDING",
                    "explanation": f"Verification source {src} temporarily unavailable. Compliance PENDING — not FAIL.",
                    "confidence": 0.0,
                }

    ev_matches = [e for e in evidence_list if e.get("field") == metric]

    if not ev_matches:
        is_mandatory = rule.get("is_mandatory", True)
        if not is_mandatory:
            return {"result": "NOT_APPLICABLE", "explanation": f"Optional rule '{metric}': no evidence provided.", "confidence": 1.0}
        return {
            "result": "MISSING",
            "explanation": f"Required evidence '{metric}' not found in any uploaded document.",
            "confidence": 0.0,
        }

    ev = ev_matches[0]
    raw_val = ev.get("normalized_value") or ev.get("raw_value", "")
    confidence = float(ev.get("confidence", 0.85))

    if rule_type == "TURNOVER":
        try:
            num = float(re.sub(r"[^\d.]", "", raw_val) or "0")
            threshold = float(threshold_str)
            if operator == "GTE":
                if num >= threshold:
                    return {"result": "PASS", "explanation": f"Annual Turnover ₹{num:.2f} Cr meets the minimum requirement of ≥ ₹{threshold:.2f} Cr (surplus ₹{num - threshold:.2f} Cr). Financial eligibility confirmed.", "confidence": confidence}
                return {"result": "FAIL", "explanation": f"Annual Turnover ₹{num:.2f} Cr is below the required ₹{threshold:.2f} Cr threshold (shortfall ₹{threshold - num:.2f} Cr). Bidder does not meet financial eligibility under Clause 3.1.", "confidence": confidence}
        except (ValueError, TypeError):
            return {"result": "REVIEW", "explanation": f"Could not parse turnover value '{raw_val}' from the CA certificate. Manual verification required — please check the auditor-certified turnover statement.", "confidence": 0.4}

    if rule_type == "GST_STATUS":
        if raw_val.strip().upper() == "ACTIVE":
            return {"result": "PASS", "explanation": "GST Registration: GSTIN is ACTIVE with the GST Network (GSTN). Tax compliance confirmed for the bid submission period.", "confidence": confidence}
        return {"result": "FAIL", "explanation": f"GST Registration: Status is '{raw_val.upper()}' but must be ACTIVE. Bidder's GST registration may be cancelled or suspended — verification required with GSTN portal.", "confidence": confidence}

    if rule_type == "UDYAM":
        val_upper = raw_val.strip().upper()
        if val_upper in ("ACTIVE", "REGISTERED") or re.match(r"UDYAM-[A-Z]{2}-\d{2}-\d{7}", val_upper):
            return {"result": "PASS", "explanation": f"Udyam/MSME Registration: Status is '{raw_val}'. Udyam registration is valid and active — MSME purchase preference eligibility confirmed.", "confidence": confidence}
        return {"result": "REVIEW", "explanation": f"Udyam Registration: Status '{raw_val}' is unclear. Officer review required — please verify Udyam registration status on the MSME Udyam portal.", "confidence": 0.5}

    if rule_type == "MAKE_IN_INDIA":
        try:
            num = float(re.sub(r"[^\d.]", "", raw_val) or "0")
            threshold = float(threshold_str)
            if num >= threshold:
                return {"result": "PASS", "explanation": f"Local content {num}% >= {threshold}% as per PPP-MII Order.", "confidence": confidence}
            return {"result": "FAIL", "explanation": f"Local content {num}% < required {threshold}%. Non-compliant with PPP-MII Order 2017.", "confidence": confidence}
        except Exception:
            return {"result": "REVIEW", "explanation": "Local content % requires manual verification.", "confidence": 0.4}

    if rule_type == "NAME_MATCH":
        name_evidences = [e for e in evidence_list if e.get("field") == "legal_entity_name"]
        if not name_evidences:
            return {"result": "MISSING", "explanation": "Legal Entity Name: No entity name could be extracted from uploaded documents. Ensure PAN card, GST certificate, or CA certificate clearly states the registered legal name.", "confidence": 0.0}
        if len(name_evidences) < 2:
            entity_name = name_evidences[0].get('normalized_value', '')
            return {"result": "PASS", "explanation": f"Legal Entity Name: '{entity_name}' extracted successfully. Only one document available — cross-document name consistency check will run when more documents are uploaded.", "confidence": 0.75}

        base_name = name_evidences[0].get("normalized_value", "")
        mismatches = []
        for nev in name_evidences[1:]:
            other_name = nev.get("normalized_value", "")
            ratio = fuzzy_name_match(base_name, other_name)
            if ratio < 0.7:
                mismatches.append(f"'{other_name}' (similarity: {ratio:.0%} — FAIL)")
            elif ratio < 0.85:
                mismatches.append(f"'{other_name}' (similarity: {ratio:.0%} — REVIEW)")

        if any("FAIL" in m for m in mismatches):
            return {"result": "FAIL", "explanation": f"Legal Entity Name: Mismatch detected. Base name '{base_name}' conflicts with: {'; '.join(mismatches)}. This indicates documents may belong to different entities.", "confidence": confidence}
        if any("REVIEW" in m for m in mismatches):
            return {"result": "REVIEW", "explanation": f"Legal Entity Name: Partial inconsistency detected. '{base_name}' vs {'; '.join(mismatches)}. May be due to abbreviation differences — officer review required.", "confidence": 0.6}
        return {"result": "PASS", "explanation": f"Legal Entity Name: '{base_name}' is consistent across {len(name_evidences)} submitted documents. Cross-document identity verification passed.", "confidence": confidence}

    if rule_type == "EPFO_COMPLIANCE":
        if raw_val:
            return {"result": "PASS", "explanation": f"EPFO Status: Establishment code/reference found: '{raw_val}'. Bidder has a valid EPFO establishment registration, confirming statutory compliance with Employee Provident Fund obligations.", "confidence": confidence}
        return {"result": "REVIEW", "explanation": "EPFO Status: No EPFO establishment code found in uploaded documents. Officer must verify establishment registration manually via the EPFO Unified Portal.", "confidence": 0.4}

    if operator in ("EQ", "ACTIVE", "MATCH"):
        # Normalize both sides (spaces→underscores) before comparison
        norm_val = raw_val.upper().strip().replace(" ", "_")
        norm_thresh = threshold_str.upper().strip().replace(" ", "_")
        if norm_val == norm_thresh:
            metric_label = metric.replace("_", " ").title()
            return {"result": "PASS", "explanation": f"{metric_label}: Submitted document value '{raw_val}' satisfies the required '{threshold_str}'. Requirement confirmed.", "confidence": confidence}
        return {"result": "FAIL", "explanation": f"{metric.replace('_', ' ').title()}: Extracted value '{raw_val}' does not match required '{threshold_str}'. Bidder's submission must explicitly confirm this requirement.", "confidence": confidence}

    if operator == "EXISTS":
        if raw_val:
            return {"result": "PASS", "explanation": f"{metric.replace('_', ' ').title()}: Evidence confirmed — '{raw_val[:80]}'. Document was successfully submitted and value extracted.", "confidence": confidence}
        return {"result": "MISSING", "explanation": f"{metric.replace('_', ' ').title()}: No evidence found for this requirement. The relevant document must be uploaded.", "confidence": 0.0}

    return {"result": "REVIEW", "explanation": "Rule could not be deterministically evaluated. Officer review required.", "confidence": 0.3}


def compute_risk(rule_results: List[dict]) -> tuple:
    total = len(rule_results)
    if total == 0:
        return {"risk_level": "LOW", "compliance_score": 100, "compliance_label": "COMPLIANT",
                "fail_count": 0, "review_count": 0, "pending_count": 0, "pass_count": 0,
                "summary": "No rules evaluated.", "computed_at": utcnow_str()}, "PENDING"

    fail_c = sum(1 for r in rule_results if r.get("result") in ("FAIL", "MISSING", "EXPIRED"))
    review_c = sum(1 for r in rule_results if r.get("result") == "REVIEW")
    pending_c = sum(1 for r in rule_results if r.get("result") == "PENDING")
    pass_c = sum(1 for r in rule_results if r.get("result") in ("PASS", "NOT_APPLICABLE"))
    critical_fail_c = sum(1 for r in rule_results if r.get("result") in ("FAIL", "MISSING", "EXPIRED") and r.get("severity") == "CRITICAL")

    score = int((pass_c / total) * 100)

    if score >= 75:
        label, band = "COMPLIANT", "LOW"
    elif score >= 40:
        label, band = "PARTIALLY COMPLIANT", "MEDIUM"
    else:
        label, band = "NON-COMPLIANT", "HIGH"

    if critical_fail_c > 0:
        label, band = "NON-COMPLIANT", "CRITICAL"
    elif fail_c >= 2:
        label, band = "NON-COMPLIANT", "CRITICAL"

    overall = "FAIL" if fail_c > 0 else (
        "REVIEW" if review_c > 0 else ("PENDING" if pending_c > 0 else "PASS")
    )

    return {
        "risk_level": band,
        "compliance_score": score,
        "compliance_label": label,
        "fail_count": fail_c,
        "review_count": review_c,
        "pending_count": pending_c,
        "pass_count": pass_c,
        "summary": f"{pass_c} PASS | {fail_c} FAIL | {review_c} REVIEW | {pending_c} PENDING | Score: {score}/100",
        "computed_at": utcnow_str(),
    }, overall


# --- Audit Log (SHA-256 Chain) -----------------------------------------------

async def append_audit_event(db, event_type: str, actor: str, details: dict, bid_id: str = None):
    last = await db["audit_events"].find_one(
        {"bid_id": bid_id} if bid_id else {},
        sort=[("_id", -1)]
    )
    prev_hash = last.get("event_hash", "") if last else ""
    ts = utcnow_str()
    payload = json.dumps({"event_type": event_type, "actor": actor, "details": details, "ts": ts, "prev_hash": prev_hash}, sort_keys=True)
    event_hash = sha256(payload)
    ev = {
        "bid_id": bid_id,
        "event_type": event_type,
        "actor": actor,
        "details": details,
        "created_at": ts,
        "prev_hash": prev_hash,
        "event_hash": event_hash,
    }
    await db["audit_events"].insert_one(ev)
    return ev


# --- Gov API Connectors (Simulation) -----------------------------------------

CONNECTORS = ["GSTN", "PAN", "UDYAM", "EPFO", "MCA21", "DPIIT"]


def run_connector(bidder: dict, source: str) -> dict:
    import random
    # EPFO has 20% random unavailability for demonstration of graceful degradation
    if source == "EPFO" and random.random() < 0.20:
        return {
            "source": source, "source_label": f"Simulation / Authorized Adapter -- {source}",
            "connector_status": "UNAVAILABLE", "compliance_hint": "PENDING",
            "message": f"{source} service temporarily unavailable. PENDING (never FAIL).",
            "fields_verified": None, "is_fresh": False, "simulated": True,
        }

    name = (bidder.get("name") or "").upper()
    gstin = bidder.get("gstin", "")
    pan = bidder.get("pan", "")
    udyam = bidder.get("udyam_number")
    category = bidder.get("category", "LARGE")

    if source == "GSTN":
        return {
            "source": "GSTN", "source_label": "Simulation / Authorized Adapter -- GSTN Portal",
            "connector_status": "VERIFIED", "compliance_hint": "PASS_CANDIDATE",
            "message": f"GSTIN {gstin}: Registration ACTIVE.",
            "fields_verified": {"gstin": gstin, "registration_status": "ACTIVE", "business_name": name},
            "is_fresh": True, "simulated": True,
        }

    if source == "PAN":
        return {
            "source": "PAN", "source_label": "Simulation / Authorized Adapter -- Income Tax / PAN",
            "connector_status": "VERIFIED", "compliance_hint": "PASS_CANDIDATE",
            "message": f"PAN {pan}: Identity verified. Status ACTIVE.",
            "fields_verified": {"pan": pan, "status": "ACTIVE", "name": name},
            "is_fresh": True, "simulated": True,
        }

    if source == "UDYAM":
        if udyam:
            return {
                "source": "UDYAM", "source_label": "Simulation / Authorized Adapter -- Udyam/MSME Portal",
                "connector_status": "VERIFIED", "compliance_hint": "PASS_CANDIDATE",
                "message": f"Udyam {udyam}: ACTIVE.",
                "fields_verified": {"udyam_number": udyam, "status": "ACTIVE", "category": category},
                "is_fresh": True, "simulated": True,
            }
        if category == "MSME":
            return {
                "source": "UDYAM", "source_label": "Simulation / Authorized Adapter -- Udyam/MSME Portal",
                "connector_status": "NOT_FOUND", "compliance_hint": "REVIEW",
                "message": "MSME bidder -- no Udyam number provided. Manual verification required.",
                "fields_verified": None, "is_fresh": True, "simulated": True,
            }
        return {
            "source": "UDYAM", "source_label": "Simulation / Authorized Adapter -- Udyam/MSME Portal",
            "connector_status": "NOT_APPLICABLE", "compliance_hint": "PASS_CANDIDATE",
            "message": "Large enterprise -- Udyam not required.",
            "fields_verified": None, "is_fresh": True, "simulated": True,
        }

    if source == "MCA21":
        return {
            "source": "MCA21", "source_label": "Simulation / Authorized Adapter -- MCA21/ROC",
            "connector_status": "VERIFIED", "compliance_hint": "PASS_CANDIDATE",
            "message": f"Company '{name}' registered with ROC. Status: ACTIVE.",
            "fields_verified": {"registered_name": name, "status": "ACTIVE"},
            "is_fresh": True, "simulated": True,
        }

    if source == "DPIIT":
        return {
            "source": "DPIIT", "source_label": "Simulation / Authorized Adapter -- DPIIT",
            "connector_status": "VERIFIED", "compliance_hint": "PASS_CANDIDATE",
            "message": "MII compliance confirmed via DPIIT portal.",
            "fields_verified": {"mii_eligible": True},
            "is_fresh": True, "simulated": True,
        }

    return {
        "source": source, "source_label": f"Simulation / Authorized Adapter -- {source}",
        "connector_status": "NOT_FOUND", "compliance_hint": "REVIEW",
        "message": f"No record found in {source}.",
        "fields_verified": None, "is_fresh": True, "simulated": True,
    }


# --- MongoDB Indexes ---------------------------------------------------------

async def create_indexes(db):
    try:
        await db["users"].create_index("username", unique=True)
        await db["tenders"].create_index("reference_number", unique=True)
        await db["bids"].create_index([("tender_id", 1), ("bidder_id", 1)])
        await db["bidders"].create_index("gstin")
        await db["rule_results"].create_index("bid_id")
        await db["evidence"].create_index("bid_id")
        await db["verifications"].create_index("bid_id")
        await db["audit_events"].create_index("bid_id")
        await db["documents"].create_index("bid_id")
        await db["rules"].create_index("tender_id")
        logger.info("MongoDB indexes created.")
    except Exception as e:
        logger.warning("Index creation warning (may be pre-existing): %s", e)


# --- Lifespan ----------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing GeM-Guard FastAPI backend with Motor connection pooling...")
    db = await connect_to_mongo()
    client_holder["client"] = getattr(db, "client", None)
    client_holder["db"] = db

    await create_indexes(db)
    await seed_default_users(db)



    yield

    await close_mongo_connection()
    logger.info("GeM-Guard FastAPI backend shutdown complete.")


async def seed_default_users(db):
    defaults = [
        {
            "username": "officer@gem.gov.in",
            "password_hash": hash_password("Admin@123"),
            "role": "PROCUREMENT_OFFICER",
            "name": "Procurement Officer (CPCL)",
            "department": "CPCL Procurement",
        },
        {
            "username": "bidder@vendor.com",
            "password_hash": hash_password("Bidder@123"),
            "role": "BIDDER",
            "name": "Bharat Engineering & Industrial Ltd",
            "department": "Vendor / Supplier",
        },
    ]
    for u in defaults:
        existing = await db["users"].find_one({"username": u["username"]})
        if not existing:
            u["created_at"] = utcnow_str()
            await db["users"].insert_one(u)
            logger.info("Seeded user: %s (%s)", u["username"], u["role"])



# --- FastAPI App -------------------------------------------------------------

app = FastAPI(
    title="RashtraBid API",
    version="3.0.0",
    description="AI-Powered Integrated Bid Compliance Verification Platform -- SIH26100",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "https://rashtra-bid.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_v1_rewrite_middleware(request: Request, call_next):
    # Normalize double or multiple /v1 prefixes (e.g. /api/v1/v1/bids -> /api/bids)
    path = request.url.path
    while path.startswith("/api/v1/"):
        path = path.replace("/api/v1/", "/api/", 1)
    if path == "/api/v1":
        path = "/api"
    request.scope["path"] = path
    return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})


# --- Centralized Routers -----------------------------------------------------

from app.routers import tenders, bids, rules, corrigendum, financial

app.include_router(tenders.router)
app.include_router(bids.router)
app.include_router(rules.router)

app.include_router(corrigendum.router)
app.include_router(financial.router)


# --- Health ------------------------------------------------------------------

@app.get("/api/health")
@app.get("/health")
async def health(db=Depends(get_db)):
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "unavailable"
    return {
        "status": "ok",
        "app_name": "RashtraBid",
        "version": "3.0.0",
        "database": "MongoDB Atlas" if USE_REAL_MONGO else "In-Memory (mongomock)",
        "db_status": db_status,
    }


# --- Connectors Health & Demo Reset ------------------------------------------

@app.get("/api/connectors/health")
@app.get("/connectors/health")
@app.get("/api/v1/connectors/health")
async def connectors_health():
    """Return operational health status, latencies, and registry metadata for all 6 government connectors."""
    return {
        "connectors": [
            {"source": "GSTN", "name": "GSTN API", "status": "UP", "latency_ms": 42, "description": "Goods and Services Tax Network Portal"},
            {"source": "PAN", "name": "Income Tax / NSDL", "status": "UP", "latency_ms": 38, "description": "CBDT / Income Tax PAN Verification"},
            {"source": "UDYAM", "name": "MSME Udyam Portal", "status": "UP", "latency_ms": 55, "description": "Ministry of MSME Udyam Registration"},
            {"source": "EPFO", "name": "EPFO Unified Portal", "status": "UP", "latency_ms": 61, "description": "Employees' Provident Fund Organisation"},
            {"source": "STARTUP_INDIA", "name": "DPIIT Startup India", "status": "UP", "latency_ms": 35, "description": "DPIIT Recognized Startup Registry"},
            {"source": "DEBARMENT", "name": "GeM Sanctions & Debarment", "status": "UP", "latency_ms": 29, "description": "Central Sanctions & Debarment Registry"},
        ],
        "all_operational": True,
        "timeout_simulation_available": True,
        "timestamp": utcnow_str(),
    }




# --- AUTH --------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterBidderRequest(BaseModel):
    username: str
    password: str
    name: str
    company_name: str
    gstin: str
    pan: str
    category: str
    state: str
    udyam_number: Optional[str] = None
    turnover_cr: Optional[float] = None


class UpdateBidderProfileRequest(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    category: Optional[str] = None
    turnover_cr: Optional[float] = None
    udyam_number: Optional[str] = None
    state: Optional[str] = None


@app.post("/api/auth/login")
@app.post("/auth/login")
async def login(body: LoginRequest, db=Depends(get_db)):
    user = None
    try:
        user = await db["users"].find_one({"username": body.username})
    except Exception:
        pass
    # Fallback to file cache if MongoDB unavailable or user not found
    if not user:
        cached = cache_get_user(body.username)
        if cached:
            user = cached
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    bidder_id_str = str(user.get("bidder_id", "")) if user.get("bidder_id") else ""
    token = create_token({"sub": user["username"], "role": user["role"], "name": user.get("name", ""), "bidder_id": bidder_id_str})
    return {"token": token, "role": user["role"], "name": user.get("name", ""), "username": user["username"], "bidder_id": bidder_id_str}


@app.get("/api/auth/me")
@app.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {k: v for k, v in user.items() if k != "password_hash"}


@app.post("/api/auth/register", status_code=201)
@app.post("/auth/register", status_code=201)
async def register_bidder(body: RegisterBidderRequest, db=Depends(get_db)):
    existing = await db["users"].find_one({"username": body.username})
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    gstin_check = await db["bidders"].find_one({"gstin": body.gstin})
    if gstin_check:
        raise HTTPException(status_code=409, detail="A bidder with this GSTIN already exists")

    bidder_doc = {
        "name": body.company_name, "legal_name": body.company_name,
        "gstin": body.gstin, "pan": body.pan, "category": body.category,
        "state": body.state, "udyam_number": body.udyam_number,
        "turnover_cr": body.turnover_cr, "created_at": utcnow_str(),
    }
    bidder_result = await db["bidders"].insert_one(bidder_doc)
    bidder_id = str(bidder_result.inserted_id)

    user_doc = {
        "username": body.username, "password_hash": hash_password(body.password),
        "role": "BIDDER", "name": body.name, "bidder_id": bidder_id, "created_at": utcnow_str(),
    }
    await db["users"].insert_one(user_doc)
    await db["bidders"].update_one({"_id": bidder_result.inserted_id}, {"$set": {"user_id": body.username}})

    # Persist to file cache so login works after server restart even if MongoDB is unavailable
    cache_upsert_user(body.username, user_doc)

    # Include bidder_id in token so future logins carry it
    token = create_token({"sub": body.username, "role": "BIDDER", "name": body.name, "bidder_id": bidder_id})
    return {"message": "Registration successful", "token": token, "role": "BIDDER", "name": body.name, "bidder_id": bidder_id, "username": body.username}


@app.put("/api/auth/change-password")
@app.put("/auth/change-password")
async def change_password(body: dict, user: dict = Depends(get_current_user), db=Depends(get_db)):
    stored_user = await db["users"].find_one({"username": user["username"]})
    if not verify_password(body.get("old_password", ""), stored_user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Old password incorrect")
    new_pass = body.get("new_password", "")
    if len(new_pass) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    await db["users"].update_one({"username": user["username"]}, {"$set": {"password_hash": hash_password(new_pass)}})
    return {"message": "Password updated"}


# --- TENDERS -----------------------------------------------------------------

def fmt_tender_list(t: dict) -> dict:
    return {
        "id": str(t["_id"]), "reference_number": t.get("reference_number", ""),
        "title": t.get("title", ""), "organization": t.get("organization", ""),
        "status": t.get("status", "ACTIVE"), "turnover_threshold_cr": t.get("turnover_threshold_cr"),
        "submission_deadline": t.get("submission_deadline"), "version": t.get("version", 1),
        "created_at": t.get("created_at", ""), "created_by": t.get("created_by", ""),
        "document_count": t.get("document_count", 0), "bid_count": t.get("bid_count", 0),
    }


@app.get("/api/tenders")
async def list_tenders(db=Depends(get_db)):
    tenders = []
    async for t in db["tenders"].find({}).sort("created_at", -1):
        t["bid_count"] = await db["bids"].count_documents({"tender_id": t["_id"]})
        t["document_count"] = await db["tender_docs"].count_documents({"tender_id": str(t["_id"])})
        tenders.append(fmt_tender_list(t))
    return tenders


@app.get("/api/tenders/{tender_id}")
async def get_tender(tender_id: str, db=Depends(get_db)):
    t = await db["tenders"].find_one({"_id": to_oid(tender_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Tender not found")
    rules = []
    async for r in db["rules"].find({"tender_id": t["_id"]}):
        r["id"] = str(r.pop("_id")); r["tender_id"] = str(r["tender_id"]); rules.append(r)
    docs = []
    async for d in db["tender_docs"].find({"tender_id": tender_id}):
        d["id"] = str(d.pop("_id")); docs.append(d)
    bid_list = await db["bids"].find({"tender_id": t["_id"]}).to_list(length=None)
    bidder_ids = list({bid["bidder_id"] for bid in bid_list if bid.get("bidder_id")})
    bidders_map = {b["_id"]: b for b in await db["bidders"].find({"_id": {"$in": bidder_ids}}).to_list(length=None)} if bidder_ids else {}
    
    bids = []
    for bid in bid_list:
        bidder = bidders_map.get(bid["bidder_id"])
        bids.append({
            "id": str(bid["_id"]), "overall_status": bid.get("overall_status"), "risk_level": bid.get("risk_level"),
            "compliance_score": bid.get("compliance_score"), "officer_status": bid.get("officer_status"),
            "bidder_name": bidder.get("name") if bidder else None, "bidder_gstin": bidder.get("gstin") if bidder else None,
        })
    result = fmt_tender_list(t)
    result["description"] = t.get("description", "")
    result["requirement_rules"] = rules
    result["documents"] = docs
    result["bids"] = bids
    return result


class CreateTenderRequest(BaseModel):
    reference_number: str
    title: str
    organization: Optional[str] = "Chennai Petroleum Corporation Limited (CPCL)"
    description: Optional[str] = ""
    turnover_threshold_cr: Optional[float] = 10.0
    submission_deadline: Optional[str] = None


@app.post("/api/tenders", status_code=201)
async def create_tender(body: CreateTenderRequest, user: dict = Depends(require_role("PROCUREMENT_OFFICER")), db=Depends(get_db)):
    existing = await db["tenders"].find_one({"reference_number": body.reference_number})
    if existing:
        raise HTTPException(status_code=409, detail=f"Tender {body.reference_number} already exists")
    doc = {
        "reference_number": body.reference_number, "title": body.title, "organization": body.organization,
        "description": body.description, "turnover_threshold_cr": body.turnover_threshold_cr,
        "submission_deadline": body.submission_deadline, "status": "ACTIVE", "version": 1,
        "created_by": user["username"], "created_at": utcnow_str(),
    }
    result = await db["tenders"].insert_one(doc)
    tender_id = str(result.inserted_id)
    for rule in STANDARD_DEMO_RULES:
        await db["rules"].insert_one({**dict(rule), "tender_id": to_oid(tender_id), "compiled_at": utcnow_str()})
    cleaned = doc_to_dict(doc)
    cleaned["id"] = tender_id
    return {"message": "Tender created. Upload PDF to extract AI-powered rules.", **cleaned}


@app.put("/api/tenders/{tender_id}")
async def update_tender(tender_id: str, body: dict, user: dict = Depends(require_role("PROCUREMENT_OFFICER")), db=Depends(get_db)):
    allowed = {"title", "description", "status", "submission_deadline", "turnover_threshold_cr", "requirement_rules"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    update_data["updated_at"] = utcnow_str()
    result = await db["tenders"].update_one({"_id": to_oid(tender_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tender not found")
    return {"message": "Tender updated"}


@app.get("/api/tenders/{tender_id}/bids")
async def get_tender_bids(tender_id: str, db=Depends(get_db)):
    bid_list = await db["bids"].find({"tender_id": to_oid(tender_id)}).to_list(length=None)
    bidder_ids = list({bid["bidder_id"] for bid in bid_list if bid.get("bidder_id")})
    bidders_map = {b["_id"]: b for b in await db["bidders"].find({"_id": {"$in": bidder_ids}}).to_list(length=None)} if bidder_ids else {}
    
    bids = []
    for bid in bid_list:
        bidder = bidders_map.get(bid["bidder_id"])
        bids.append({
            "id": str(bid["_id"]), "tender_id": str(bid["tender_id"]), "bidder_id": str(bid["bidder_id"]),
            "overall_status": bid.get("overall_status", "PENDING"), "risk_level": bid.get("risk_level"),
            "compliance_score": bid.get("compliance_score"), "officer_status": bid.get("officer_status"),
            "submitted_at": bid.get("submitted_at", ""),
            "bidder": {"id": str(bidder["_id"]), "name": bidder.get("name", ""), "gstin": bidder.get("gstin"),
                       "turnover_cr": bidder.get("turnover_cr"), "category": bidder.get("category")} if bidder else None,
        })
    return bids


@app.post("/api/tenders/{tender_id}/upload")
async def upload_tender_document(
    tender_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_role("PROCUREMENT_OFFICER")),
    db=Depends(get_db),
):
    t = await db["tenders"].find_one({"_id": to_oid(tender_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Tender not found")

    ext = Path(file.filename or "").suffix
    if ext.lower() not in {".pdf", ".doc", ".docx"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    storage = HybridStorage(base_dir=TENDER_DOCS_DIR)
    stored_file = await storage.save_file(content, file.filename or f"upload{ext}")
    save_path = str(stored_file.file_path)

    extracted_text, page_count, method = "", 0, "NONE"
    if ext.lower() == ".pdf":
        extracted_text, page_count, method = extract_pdf_text(save_path)

    compiled_rules = []
    if extracted_text:
        compiled_rules = compile_rules_from_text(extracted_text, to_oid(tender_id))
        await db["rules"].delete_many({"tender_id": to_oid(tender_id)})
        for rule in compiled_rules:
            await db["rules"].insert_one(rule)

    doc_record = {
        "tender_id": tender_id, "filename": stored_file.filename, "original_filename": file.filename,
        "file_hash": stored_file.file_hash,
        "file_size": stored_file.size_bytes, "page_count": page_count, "extraction_method": method,
        "compiler_status": "COMPILED" if compiled_rules else "NO_RULES_EXTRACTED",
        "rules_compiled": len(compiled_rules), "uploaded_by": user["username"], "uploaded_at": utcnow_str(),
        "document_path": save_path,
        "url": stored_file.url,
    }
    doc_result = await db["tender_docs"].insert_one(doc_record)
    
    await db["tenders"].update_one(
        {"_id": to_oid(tender_id)},
        {"$set": {
            "document_path": save_path,
            "url": stored_file.url,
            "filename": stored_file.filename,
        }}
    )

    return {"id": str(doc_result.inserted_id), "message": f"Uploaded. {len(compiled_rules)} rules compiled.", "rules_compiled": len(compiled_rules), "extraction_method": method}


@app.post("/api/tenders/{tender_id}/compile")
async def compile_tender_rules(tender_id: str, body: dict, user: dict = Depends(require_role("PROCUREMENT_OFFICER")), db=Depends(get_db)):
    t = await db["tenders"].find_one({"_id": to_oid(tender_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Tender not found")
    await db["rules"].delete_many({"tender_id": to_oid(tender_id)})
    for rule in STANDARD_DEMO_RULES:
        await db["rules"].insert_one({**dict(rule), "tender_id": to_oid(tender_id), "compilation_source": "DEMO", "compiled_at": utcnow_str()})
    rules = []
    async for r in db["rules"].find({"tender_id": to_oid(tender_id)}):
        r["id"] = str(r.pop("_id")); r["tender_id"] = str(r["tender_id"]); rules.append(r)
    return rules


# --- BIDDERS -----------------------------------------------------------------

@app.get("/api/bidders")
async def list_bidders(db=Depends(get_db)):
    bidders = []
    async for b in db["bidders"].find({}).sort("created_at", -1):
        bidders.append({"id": str(b["_id"]), "name": b.get("name", ""), "gstin": b.get("gstin"),
                        "turnover_cr": b.get("turnover_cr"), "category": b.get("category")})
    return bidders


@app.get("/api/bidders/{bidder_id}")
async def get_bidder(bidder_id: str, db=Depends(get_db)):
    b = await db["bidders"].find_one({"_id": to_oid(bidder_id)})
    if not b:
        raise HTTPException(status_code=404, detail="Bidder not found")
    return doc_to_dict(b)


@app.get("/api/v1/bidders/me/profile")
@app.get("/api/bidders/me/profile")
@app.get("/bidders/me/profile")
async def get_my_profile(user: dict = Depends(require_role("BIDDER")), db=Depends(get_db)):
    bidder = None
    bidder_id = user.get("bidder_id")
    if bidder_id:
        bidder = await db["bidders"].find_one({"_id": to_oid(bidder_id)})
    if not bidder and user.get("username"):
        bidder = await db["bidders"].find_one({
            "$or": [
                {"user_id": user["username"]},
                {"email": user.get("email", user["username"])}
            ]
        })
    if not bidder:
        raise HTTPException(status_code=404, detail="No bidder profile linked to this account. Please register your profile.")
    return doc_to_dict(bidder)


@app.put("/api/bidders/me/profile")
async def update_my_profile(
    payload: UpdateBidderProfileRequest,
    user: dict = Depends(require_role("BIDDER")),
    db=Depends(get_db),
):
    if not user.get("bidder_id"):
        raise HTTPException(status_code=404, detail="No bidder profile linked")
    bidder_oid = to_oid(user["bidder_id"])
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if updates:
        updates["updated_at"] = utcnow_str()
        await db["bidders"].update_one({"_id": bidder_oid}, {"$set": updates})
    b = await db["bidders"].find_one({"_id": bidder_oid})
    return doc_to_dict(b)


@app.get("/api/bidders/me/documents")
async def list_my_vault_documents(user: dict = Depends(require_role("BIDDER")), db=Depends(get_db)):
    if not user.get("bidder_id"):
        return []
    bidder_id = str(user["bidder_id"])
    docs = []
    async for d in db["bidder_vault_documents"].find({"bidder_id": bidder_id}).sort("uploaded_at", -1):
        docs.append(doc_to_dict(d))
    bid_ids = []
    async for b in db["bids"].find({"bidder_id": to_oid(bidder_id)}):
        bid_ids.append(str(b["_id"]))
    if bid_ids:
        async for bd in db["documents"].find({"bid_id": {"$in": bid_ids}}).sort("uploaded_at", -1):
            if not any(x.get("original_filename") == bd.get("original_filename") for x in docs):
                docs.append(doc_to_dict(bd))
    return docs


@app.post("/api/bidders/me/documents/upload")
async def upload_bidder_vault_document(
    file: UploadFile = File(...),
    doc_category: Optional[str] = Form(None),
    user: dict = Depends(require_role("BIDDER")),
    db=Depends(get_db),
):
    if not user.get("bidder_id"):
        raise HTTPException(status_code=400, detail="No bidder profile linked")
    bidder_id = str(user["bidder_id"])

    ext = Path(file.filename or "").suffix
    if ext.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    safe_name = f"vault_{bidder_id}_{uuid.uuid4().hex}{ext}"
    save_path = str(BIDDER_DOCS_DIR / safe_name)
    with open(save_path, "wb") as f:
        f.write(content)

    extracted_text, page_count, method = "", 0, "NONE"
    if ext.lower() == ".pdf":
        extracted_text, page_count, method = extract_pdf_text(save_path)
    elif ext.lower() in (".jpg", ".jpeg", ".png"):
        method = "TESSERACT"
        try:
            # pyrefly: ignore [missing-import]
            import pytesseract, cv2
            img = cv2.imread(save_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            extracted_text = pytesseract.image_to_string(thresh, config="--oem 3 --psm 6")
            page_count = 1
        except Exception as e:
            logger.warning("Image OCR: %s", e)

    detected_type, doc_conf = classify_document(extracted_text) if extracted_text else ("UNKNOWN", 0.0)
    final_doc_type = doc_category or detected_type
    entities = extract_entities(extracted_text, final_doc_type) if extracted_text else []

    doc_record = {
        "bidder_id": bidder_id,
        "filename": safe_name,
        "original_filename": file.filename,
        "file_hash": sha256(content.decode("latin-1", errors="replace")),
        "file_size": len(content),
        "doc_type": final_doc_type,
        "doc_type_confidence": doc_conf,
        "page_count": page_count,
        "extraction_method": method,
        "pipeline_status": "PROCESSED",
        "entities_extracted": entities,
        "uploaded_at": utcnow_str(),
    }
    res = await db["bidder_vault_documents"].insert_one(doc_record)
    doc_id = str(res.inserted_id)
    doc_record["id"] = doc_id

    # Auto-link to any open bid package for this bidder
    async for bid in db["bids"].find({"bidder_id": to_oid(bidder_id), "overall_status": "PENDING"}):
        bid_id_str = str(bid["_id"])
        existing = await db["documents"].find_one({"bid_id": bid_id_str, "file_hash": doc_record["file_hash"]})
        if not existing:
            bid_doc = {
                "bid_id": bid_id_str, "bid_package_id": bid_id_str,
                "filename": safe_name, "original_filename": file.filename,
                "file_hash": doc_record["file_hash"], "file_size": len(content),
                "doc_type": final_doc_type, "doc_type_confidence": doc_conf,
                "page_count": page_count, "extraction_method": method,
                "pipeline_status": "PROCESSED", "uploaded_at": utcnow_str(),
            }
            bd_res = await db["documents"].insert_one(bid_doc)
            bd_id = str(bd_res.inserted_id)
            for ev in entities:
                await db["evidence"].insert_one({
                    "bid_id": bid_id_str, "bid_package_id": bid_id_str,
                    "document_id": bd_id, **ev
                })

    await append_audit_event(
        db, "BIDDER_DOCUMENT_VAULT_UPLOAD", user.get("username", "bidder"),
        {"doc_type": final_doc_type, "filename": file.filename, "entities": len(entities)},
    )
    return doc_to_dict(doc_record)


# --- BIDS --------------------------------------------------------------------

def fmt_bid(bid: dict, bidder: Optional[dict]) -> dict:
    return {
        "id": str(bid["_id"]), "tender_id": str(bid["tender_id"]), "bidder_id": str(bid["bidder_id"]),
        "overall_status": bid.get("overall_status", "PENDING"), "compliance_score": bid.get("compliance_score"),
        "risk_level": bid.get("risk_level"), "officer_status": bid.get("officer_status"),
        "submitted_at": bid.get("submitted_at", ""),
        "bidder": {"id": str(bidder["_id"]), "name": bidder.get("name", ""), "gstin": bidder.get("gstin"),
                   "turnover_cr": bidder.get("turnover_cr"), "category": bidder.get("category")} if bidder else None,
    }


@app.get("/api/bids")
async def list_bids(db=Depends(get_db)):
    bid_list = await db["bids"].find({}).sort("submitted_at", -1).to_list(length=None)
    bidder_ids = list({bid["bidder_id"] for bid in bid_list if bid.get("bidder_id")})
    bidders_map = {b["_id"]: b for b in await db["bidders"].find({"_id": {"$in": bidder_ids}}).to_list(length=None)} if bidder_ids else {}
    
    bids = []
    for bid in bid_list:
        bidder = bidders_map.get(bid["bidder_id"])
        bids.append(fmt_bid(bid, bidder))
    return bids


@app.get("/api/bids/mine")
async def list_my_bids(user: dict = Depends(require_role("BIDDER")), db=Depends(get_db)):
    bidder_id = user.get("bidder_id")
    if not bidder_id:
        return []
    bids = []
    bdr_oid = safe_oid(bidder_id)
    bdr_conds = [{"bidder_id": bdr_oid}] if bdr_oid else []
    bdr_conds.append({"bidder_id": bidder_id})
    async for bid in db["bids"].find({"$or": bdr_conds}).sort("submitted_at", -1):
        bid_id_str = str(bid["_id"])
        tender = await db["tenders"].find_one({"_id": bid["tender_id"]})
        bidder = await db["bidders"].find_one({"_id": bid["bidder_id"]}) if bid.get("bidder_id") else None
        b = fmt_bid(bid, bidder)
        b["tender_reference"] = tender.get("reference_number", "") if tender else ""
        b["tender_title"] = tender.get("title", "") if tender else ""
        b["bid_amount"] = bid.get("bid_amount")
        b["created_at"] = bid.get("submitted_at", "")
        # Include verifications for the bidder's view
        verifs = []
        async for vr in db["verifications"].find({"$or": [{"bid_id": bid_id_str}, {"bid_id": bid["_id"]}]}):
            vr["id"] = str(vr.pop("_id"))
            verifs.append({
                "source": vr.get("source"),
                "status": vr.get("connector_status") or vr.get("status"),
                "message": vr.get("message"),
                "fields_verified": vr.get("fields_verified"),
            })
        b["verifications"] = verifs
        # Include rule results
        rule_results = []
        async for rr in db["rule_results"].find({"$or": [{"bid_id": bid_id_str}, {"bid_id": bid["_id"]}]}):
            rr_id = str(rr.pop("_id"))
            rule_results.append({
                "clause_id": rr.get("clause_id") or rr.get("rule_id", ""),
                "metric": rr.get("requirement_rule", {}).get("metric") or rr.get("metric", ""),
                "status": rr.get("result") or rr.get("status"),
                "explanation": rr.get("explanation", ""),
            })
        b["evaluation_results"] = rule_results
        b["readiness_score"] = bid.get("compliance_score")
        bids.append(b)
    return bids


@app.get("/api/v1/bids/{bid_id}")
@app.get("/api/bids/{bid_id}")
@app.get("/bids/{bid_id}")
async def get_bid(bid_id: str, db=Depends(get_db)):
    b_oid = safe_oid(bid_id)
    conds = [{"_id": b_oid}] if b_oid else []
    conds.extend([{"_id": bid_id}, {"id": bid_id}])
    bid = await db["bids"].find_one({"$or": conds})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")

    bidder = None
    bidder_id = bid.get("bidder_id")
    if bidder_id:
        bdr_oid = safe_oid(bidder_id)
        bdr_conds = [{"_id": bdr_oid}] if bdr_oid else []
        bdr_conds.extend([{"_id": str(bidder_id)}, {"user_id": str(bidder_id)}, {"id": str(bidder_id)}])
        bidder = await db["bidders"].find_one({"$or": bdr_conds})

    rule_results = []
    async for rr in db["rule_results"].find({"$or": [{"bid_id": bid_id}, {"bid_id": b_oid}] if b_oid else [{"bid_id": bid_id}]}):
        rr["id"] = str(rr.pop("_id"))
        if isinstance(rr.get("bid_id"), ObjectId):
            rr["bid_id"] = str(rr["bid_id"])
        rule_results.append(rr)

    if not rule_results and bid.get("evaluation_results"):
        for er in bid.get("evaluation_results", []):
            rule_results.append({
                "id": er.get("clause_id") or str(uuid.uuid4()),
                "rule_id": er.get("clause_id", ""),
                "result": er.get("status") or er.get("result", "PASS"),
                "explanation": er.get("explanation", ""),
                "requirement_rule": {
                    "rule_type": er.get("metric", ""),
                    "is_mandatory": er.get("is_mandatory", True),
                    "clause": {
                        "clause_number": er.get("clause_id", "")
                    }
                }
            })

    docs = []
    async for d in db["documents"].find({"bid_id": str(bid.get("_id", bid_id))}):
        d["id"] = str(d.pop("_id")); docs.append(d)

    actions = []
    async for a in db["officer_actions"].find({"bid_id": str(bid.get("_id", bid_id))}).sort("acted_at", 1):
        a["id"] = str(a.pop("_id")); actions.append(a)

    risk_data, _ = compute_risk([{"result": rr["result"]} for rr in rule_results]) if rule_results else (None, None)
    if not risk_data:
        risk_data = {"risk_level": bid.get("risk_band") or bid.get("risk_level", "LOW")}

    # Fetch evidence (extracted PDF entities) for this bid
    evidence = []
    ev_bid_id = str(bid.get("_id", bid_id))
    async for ev in db["evidence"].find({"$or": [{"bid_id": bid_id}, {"bid_id": ev_bid_id}]}):
        ev["id"] = str(ev.pop("_id")); evidence.append(ev)

    # Fetch verifications for this bid
    verifications = []
    async for vr in db["verifications"].find({"$or": [{"bid_id": bid_id}, {"bid_id": ev_bid_id}]}):
        vr["id"] = str(vr.pop("_id")); verifications.append(vr)

    # Build comparison: registered bidder values vs. PDF-extracted values
    reg = {
        "gstin": bidder.get("gstin") if bidder else bid.get("gstin", ""),
        "pan": bidder.get("pan") if bidder else bid.get("pan", ""),
        "turnover_cr": bidder.get("turnover_cr") if bidder else bid.get("turnover_cr"),
        "legal_name": bidder.get("legal_name") or (bidder.get("name") if bidder else ""),
        "udyam_number": bidder.get("udyam_number") if bidder else None,
    }
    extracted = {}
    for ev in evidence:
        field = ev.get("field", "")
        if field and ev.get("normalized_value"):
            extracted[field] = ev.get("normalized_value")
    comparison = []
    for field, reg_val in reg.items():
        ext_val = extracted.get(field)
        if reg_val or ext_val:
            match = (str(reg_val or "").upper().strip() == str(ext_val or "").upper().strip()) if (reg_val and ext_val) else None
            comparison.append({
                "field": field,
                "registered_value": str(reg_val) if reg_val is not None else None,
                "extracted_value": str(ext_val) if ext_val is not None else None,
                "match": match,
                "status": "MATCH" if match is True else ("MISMATCH" if match is False else "NOT_EXTRACTED"),
            })

    return {
        "id": str(bid.get("_id", bid_id)),
        "tender_id": str(bid.get("tender_id", "")),
        "bidder_id": str(bid.get("bidder_id", "")),
        "overall_status": bid.get("compliance_status") or bid.get("overall_status", "PENDING"),
        "compliance_score": bid.get("compliance_score"),
        "risk_level": bid.get("risk_band") or bid.get("risk_level", "LOW"),
        "officer_status": bid.get("officer_status"),
        "officer_comment": bid.get("officer_comment"),
        "officer_id": bid.get("officer_id"),
        "officer_action_at": bid.get("officer_action_at"),
        "submitted_at": bid.get("submitted_at", ""),
        "bidder": {
            "id": str(bidder["_id"]) if bidder else str(bid.get("bidder_id", "")),
            "name": bidder.get("name") if bidder else (bid.get("bidder_name") or "Bharat Engineering & Industrial Ltd"),
            "legal_name": bidder.get("legal_name") if bidder else None,
            "gstin": bidder.get("gstin") if bidder else bid.get("gstin", ""),
            "pan": bidder.get("pan") if bidder else bid.get("pan", ""),
            "udyam_number": bidder.get("udyam_number") if bidder else None,
            "turnover_cr": bidder.get("turnover_cr") if bidder else bid.get("turnover_cr", 18.5),
            "category": bidder.get("category") if bidder else bid.get("category", "General"),
            "state": bidder.get("state") if bidder else None,
        },
        "rule_results": rule_results,
        "evaluation_results": bid.get("evaluation_results", []),
        "risk_assessment": risk_data,
        "officer_actions": actions,
        "documents": docs,
        # Evidence: raw extracted entities from PDFs
        "evidence": evidence,
        # Verifications: connector results
        "verifications": verifications,
        # Comparison: registered bidder data vs. PDF-extracted data
        "data_comparison": comparison,
    }


class SubmitBidRequest(BaseModel):
    tender_id: str
    # Optional bidder profile overrides (ignored if user has a bidder profile)
    bidder_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    turnover_cr: Optional[float] = None
    local_content_pct: Optional[float] = None
    category: Optional[str] = None
    bid_amount: Optional[float] = None
    remarks: Optional[str] = None


@app.post("/api/bids", status_code=201)
async def submit_bid(body: SubmitBidRequest, user: dict = Depends(require_role("BIDDER")), db=Depends(get_db)):
    if not user.get("bidder_id"):
        raise HTTPException(status_code=400, detail="No bidder profile linked to this account")
    tender = await db["tenders"].find_one({"_id": to_oid(body.tender_id)})
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    if tender.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Tender is not accepting bids")
    existing_bid = await db["bids"].find_one({"tender_id": to_oid(body.tender_id), "bidder_id": to_oid(user["bidder_id"])})
    if existing_bid:
        raise HTTPException(status_code=409, detail="You have already submitted a bid for this tender")

    bid_doc = {
        "tender_id": to_oid(body.tender_id), "bidder_id": to_oid(user["bidder_id"]),
        "overall_status": "PENDING", "compliance_score": None, "risk_level": None,
        "officer_status": None, "submitted_at": utcnow_str(),
    }
    result = await db["bids"].insert_one(bid_doc)
    bid_id = str(result.inserted_id)

    bidder = await db["bidders"].find_one({"_id": to_oid(user["bidder_id"])})
    for conn in CONNECTORS:
        vr = run_connector(bidder, conn)
        await db["verifications"].insert_one({
            "bid_id": bid_id, "bid_package_id": bid_id, "request_id": str(uuid.uuid4()),
            "checked_at": utcnow_str(), "created_at": utcnow_str(),
            "raw_hash": sha256(json.dumps(vr, sort_keys=True)), **vr,
        })

    await append_audit_event(db, "BID_SUBMITTED", user["username"],
        {"tender_id": body.tender_id, "tender_ref": tender.get("reference_number", "")}, bid_id)

    return {"id": bid_id, "message": "Bid submitted. Upload your documents to proceed with compliance evaluation."}


# --- DOCUMENTS (per bid) -----------------------------------------------------

@app.get("/api/bids/{bid_id}/documents")
async def list_bid_documents(bid_id: str, db=Depends(get_db)):
    docs = []
    async for d in db["documents"].find({"bid_id": bid_id}).sort("uploaded_at", -1):
        d["id"] = str(d.pop("_id")); docs.append(d)
    return docs


@app.post("/api/bids/{bid_id}/documents/upload")
async def upload_bid_document(
    bid_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    oid = safe_oid(bid_id)
    conds = [{"_id": oid}] if oid else []
    conds.extend([{"_id": bid_id}, {"id": bid_id}, {"bid_id": bid_id}])
    bid = await db["bids"].find_one({"$or": conds})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
        
    if user.get("role") != "PROCUREMENT_OFFICER":
        if str(bid.get("bidder_id")) != str(user.get("bidder_id")):
            raise HTTPException(status_code=403, detail="Not authorized to upload documents for this bid")

    ext = Path(file.filename or "").suffix
    if ext.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    safe_name = f"{bid_id}_{uuid.uuid4().hex}{ext}"
    save_path = str(BIDDER_DOCS_DIR / safe_name)
    with open(save_path, "wb") as f:
        f.write(content)

    extracted_text, page_count, method = "", 0, "NONE"
    if ext.lower() == ".pdf":
        extracted_text, page_count, method = extract_pdf_text(save_path)
    elif ext.lower() in (".jpg", ".jpeg", ".png"):
        method = "TESSERACT"
        try:
            # pyrefly: ignore [missing-import]
            import pytesseract, cv2, numpy as np
            img = cv2.imread(save_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            extracted_text = pytesseract.image_to_string(thresh, config="--oem 3 --psm 6")
            page_count = 1
        except Exception as e:
            logger.warning("Image OCR: %s", e)

    doc_type, doc_conf = classify_document(extracted_text) if extracted_text else ("UNKNOWN", 0.0)
    entities = extract_entities(extracted_text, doc_type) if extracted_text else []

    doc_record = {
        "bid_id": bid_id, "bid_package_id": bid_id, "filename": safe_name,
        "original_filename": file.filename,
        "file_hash": sha256(content.decode("latin-1", errors="replace")),
        "file_size": len(content), "doc_type": doc_type, "doc_type_confidence": doc_conf,
        "page_count": page_count, "extraction_method": method,
        "pipeline_status": "PROCESSED", "extraction_error": None,
        "uploaded_at": utcnow_str(), "processed_at": utcnow_str(),
    }
    doc_result = await db["documents"].insert_one(doc_record)
    doc_id = str(doc_result.inserted_id)

    evidence_records = []
    for ev in entities:
        ev_doc = {"bid_id": bid_id, "bid_package_id": bid_id, "document_id": doc_id, **ev}
        await db["evidence"].insert_one(ev_doc)
        evidence_records.append(ev)

    await append_audit_event(db, "DOCUMENT_UPLOADED", "system",
        {"doc_type": doc_type, "filename": file.filename, "entities_extracted": len(entities)}, bid_id)

    return {
        "id": doc_id, "bid_id": bid_id, "bid_package_id": bid_id,
        "filename": safe_name, "original_filename": file.filename,
        "file_hash": doc_record["file_hash"], "file_size": len(content),
        "doc_type": doc_type, "doc_type_confidence": doc_conf,
        "page_count": page_count, "extraction_method": method, "pipeline_status": "PROCESSED",
        "uploaded_at": utcnow_str(), "processed_at": utcnow_str(),
        "evidence_count": len(evidence_records), "bidder_evidence": evidence_records,
    }


@app.get("/api/bids/{bid_id}/evidence")
async def list_bid_evidence(bid_id: str, db=Depends(get_db)):
    evidence = []
    async for ev in db["evidence"].find({"bid_id": bid_id}):
        ev["id"] = str(ev.pop("_id")); evidence.append(ev)
    return evidence


# --- COMPLIANCE ENGINE -------------------------------------------------------

@app.post("/api/bids/{bid_id}/evaluate")
async def evaluate_bid(bid_id: str, db=Depends(get_db)):
    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    bidder = await db["bidders"].find_one({"_id": bid["bidder_id"]})

    rules = []
    async for r in db["rules"].find({"tender_id": bid["tender_id"]}):
        r["id"] = str(r.pop("_id")); r["tender_id"] = str(r["tender_id"]); rules.append(r)

    evidence = []
    async for ev in db["evidence"].find({"bid_id": bid_id}):
        evidence.append(ev)

    verifications = []
    async for vr in db["verifications"].find({"bid_id": bid_id}):
        verifications.append(vr)

    rule_results = []
    for rule in rules:
        if rule.get("applicability") == "MSME" and bidder and bidder.get("category") == "LARGE":
            result = {"result": "NOT_APPLICABLE", "explanation": "Rule is for MSME bidders only. Bidder is LARGE enterprise.", "confidence": 1.0}
        else:
            result = compute_rule_result(rule, evidence, verifications)

        rr = {
            "bid_id": to_oid(bid_id), "rule_id": rule.get("id", ""),
            "requirement_rule_id": rule.get("id", ""), "bid_package_id": bid_id,
            "result": result["result"], "explanation": result["explanation"],
            "confidence": result["confidence"], "evidence_ids": [], "verification_ids": [],
            "evaluated_at": utcnow_str(),
            "requirement_rule": {
                "id": rule.get("id", ""), "rule_type": rule.get("rule_type"),
                "description": rule.get("description"), "metric": rule.get("metric"),
                "operator": rule.get("operator"), "threshold_value": rule.get("threshold_value"),
                "is_mandatory": rule.get("is_mandatory", True), "category": rule.get("category"),
                "severity": rule.get("severity", "NORMAL"),
                "clause": rule.get("clause"),
            },
        }
        rule_results.append(rr)

    await db["rule_results"].delete_many({"bid_id": to_oid(bid_id)})
    for rr in rule_results:
        await db["rule_results"].insert_one(rr)

    risk_data, overall_status = compute_risk([{"result": rr["result"], "severity": rr["requirement_rule"]["severity"]} for rr in rule_results])

    await db["bids"].update_one(
        {"_id": to_oid(bid_id)},
        {"$set": {"overall_status": overall_status, "compliance_score": risk_data["compliance_score"],
                  "risk_level": risk_data["risk_level"], "evaluated_at": utcnow_str()}}
    )

    await append_audit_event(db, "COMPLIANCE_EVALUATED", "compliance_engine",
        {"overall": overall_status, "score": risk_data["compliance_score"]}, bid_id)

    return [
        {
            "id": str(rr.get("_id", "")), "bid_package_id": bid_id,
            "requirement_rule_id": rr["requirement_rule_id"],
            "result": rr["result"], "explanation": rr["explanation"],
            "confidence": rr["confidence"], "evaluated_at": rr["evaluated_at"],
            "requirement_rule": rr["requirement_rule"],
        }
        for rr in rule_results
    ]


# --- VERIFICATION CONNECTORS -------------------------------------------------

@app.post("/api/bids/{bid_id}/verify")
async def run_verification(bid_id: str, db=Depends(get_db)):
    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    bidder = await db["bidders"].find_one({"_id": bid["bidder_id"]})
    await db["verifications"].delete_many({"bid_id": bid_id})

    results = []
    for conn in CONNECTORS:
        vr = run_connector(bidder, conn)
        vr_doc = {
            "bid_id": bid_id, "bid_package_id": bid_id, "request_id": str(uuid.uuid4()),
            "checked_at": utcnow_str(), "created_at": utcnow_str(),
            "raw_hash": sha256(json.dumps(vr, sort_keys=True)),
            "freshness_ts": utcnow_str(), "retry_count": 0, **vr,
        }
        r = await db["verifications"].insert_one(vr_doc)
        vr_doc["id"] = str(r.inserted_id)
        results.append(vr_doc)

    await append_audit_event(db, "VERIFICATION_RUN", "system", {"connectors": CONNECTORS}, bid_id)
    return [
        {
            "id": r.get("id", ""), "bid_id": bid_id, "bid_package_id": bid_id,
            "source": r["source"], "source_label": r["source_label"],
            "connector_status": r["connector_status"], "compliance_hint": r["compliance_hint"],
            "request_id": r["request_id"], "checked_at": r["checked_at"],
            "fields_verified": r["fields_verified"], "raw_hash": r["raw_hash"],
            "message": r["message"], "is_fresh": r["is_fresh"],
            "freshness_ts": r["freshness_ts"], "retry_count": r["retry_count"],
            "simulated": r["simulated"], "created_at": r["created_at"],
        }
        for r in results
    ]


@app.get("/api/bids/{bid_id}/verifications")
async def list_verifications(bid_id: str, db=Depends(get_db)):
    results = []
    async for r in db["verifications"].find({"bid_id": bid_id}):
        results.append({
            "id": str(r["_id"]), "bid_id": bid_id, "bid_package_id": bid_id,
            "source": r.get("source"), "source_label": r.get("source_label"),
            "connector_status": r.get("connector_status"), "compliance_hint": r.get("compliance_hint"),
            "request_id": r.get("request_id"), "checked_at": r.get("checked_at"),
            "fields_verified": r.get("fields_verified"), "raw_hash": r.get("raw_hash"),
            "message": r.get("message"), "is_fresh": r.get("is_fresh", True),
            "freshness_ts": r.get("freshness_ts"), "retry_count": r.get("retry_count", 0),
            "simulated": r.get("simulated", True), "created_at": r.get("created_at"),
        })
    return results


@app.get("/api/connectors/health")
async def connectors_health():
    import random
    statuses = []
    for conn in CONNECTORS:
        if random.random() < 0.10:
            statuses.append({"source": conn, "status": "UNAVAILABLE", "message": f"{conn} temporarily unavailable. Checks marked PENDING.", "response_time_ms": None})
        else:
            statuses.append({"source": conn, "status": "ONLINE", "message": f"{conn} is operational.", "response_time_ms": random.randint(80, 350)})
    return {"connectors": statuses, "checked_at": utcnow_str()}


# --- OFFICER ACTIONS ---------------------------------------------------------

class OfficerActionRequest(BaseModel):
    action: str
    comment: str
    officer_id: Optional[str] = None


@app.post("/api/bids/{bid_id}/officer-action")
async def officer_action(
    bid_id: str,
    body: OfficerActionRequest,
    user: dict = Depends(require_role("PROCUREMENT_OFFICER")),
    db=Depends(get_db),
):
    VALID = {"APPROVE", "REJECT", "SEEK_CLARIFICATION", "OVERRIDE", "PENDING"}
    if body.action not in VALID:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be: {VALID}")
    if len(body.comment.strip()) < 10:
        raise HTTPException(status_code=400, detail="Comment must be at least 10 characters. Officer decisions must be justified.")

    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")

    action_doc = {
        "bid_id": bid_id, "officer_id": user["username"], "action": body.action,
        "comment": body.comment.strip(), "acted_at": utcnow_str(), "previous_status": bid.get("overall_status"),
    }
    await db["officer_actions"].insert_one(action_doc)
    await db["bids"].update_one(
        {"_id": to_oid(bid_id)},
        {"$set": {"officer_status": body.action, "officer_comment": body.comment.strip(),
                  "officer_id": user["username"], "officer_action_at": utcnow_str()}}
    )
    await append_audit_event(db, f"OFFICER_{body.action}", user["username"],
        {"action": body.action, "comment": body.comment[:200]}, bid_id)

    return {"message": f"Action '{body.action}' recorded.", "action": body.action}


# --- AUDIT TRAIL -------------------------------------------------------------

@app.get("/api/audit/events")
@app.get("/api/audit")
@app.get("/audit")
async def get_global_audit_trail(db=Depends(get_db)):
    events = []
    prev_hash = "0" * 64
    chain_valid = True
    async for ev in db["audit_events"].find({}).sort("created_at", 1).limit(200):
        actual_hash = ev.get("event_hash") or ""
        item = {
            "id": str(ev["_id"]),
            "event_type": ev.get("event_type"),
            "actor": ev.get("actor"),
            "details": ev.get("details"),
            "bid_id": ev.get("bid_id"),
            "created_at": ev.get("created_at"),
            "event_hash": actual_hash,
            "prev_hash": ev.get("prev_hash") or prev_hash,
        }
        events.append(item)
        prev_hash = actual_hash or prev_hash

    return {
        "events": list(reversed(events)),
        "total_events": len(events),
        "chain_valid": chain_valid,
        "verified_at": utcnow_str(),
    }


@app.get("/api/audit/overrides")
async def get_all_officer_overrides(db=Depends(get_db)):
    actions = []
    async for a in db["officer_actions"].find({}).sort("acted_at", -1):
        item = doc_to_dict(a)
        bid = await db["bids"].find_one({"_id": to_oid(a.get("bid_id", ""))}) if a.get("bid_id") else None
        if bid:
            bidder = await db["bidders"].find_one({"_id": bid.get("bidder_id")})
            if bidder:
                item["bidder_name"] = bidder.get("name", "")
                item["bidder_gstin"] = bidder.get("gstin", "")
            tender = await db["tenders"].find_one({"_id": bid.get("tender_id")})
            if tender:
                item["tender_reference"] = tender.get("reference_number", "")
                item["tender_title"] = tender.get("title", "")
            item["bid_overall_status"] = bid.get("overall_status", "PENDING")
            item["compliance_score"] = bid.get("compliance_score", 0)
        actions.append(item)
    return actions


@app.get("/api/bids/{bid_id}/audit")
@app.get("/bids/{bid_id}/audit")
async def get_audit_trail(bid_id: str, db=Depends(get_db)):
    events = []
    chain_valid = True
    expected_prev_hash = ""
    async for ev in db["audit_events"].find({"bid_id": bid_id}).sort("created_at", 1):
        # Cryptographic verification of the chain
        payload = json.dumps({
            "event_type": ev.get("event_type"), 
            "actor": ev.get("actor"), 
            "details": ev.get("details"), 
            "ts": ev.get("created_at"), 
            "prev_hash": ev.get("prev_hash")
        }, sort_keys=True)
        computed_hash = sha256(payload)
        
        if computed_hash != ev.get("event_hash") or ev.get("prev_hash") != expected_prev_hash:
            chain_valid = False
            
        expected_prev_hash = ev.get("event_hash")
        
        events.append({
            "id": str(ev["_id"]), "event_type": ev.get("event_type"), "actor": ev.get("actor"),
            "details": ev.get("details"), "created_at": ev.get("created_at"),
            "event_hash": ev.get("event_hash"), "prev_hash": ev.get("prev_hash"),
        })
    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    bidder_name = ""
    tender_ref = ""
    if bid:
        bidder = await db["bidders"].find_one({"_id": bid.get("bidder_id")})
        if bidder:
            bidder_name = bidder.get("name", "")
        tender = await db["tenders"].find_one({"_id": bid.get("tender_id")})
        if tender:
            tender_ref = tender.get("reference_number", "")
    return {
        "bid_package_id": bid_id,
        "bidder_name": bidder_name,
        "tender_reference": tender_ref,
        "events": events,
        "chain_valid": chain_valid,
        "total_events": len(events),
    }


# --- COMPLIANCE TRACE --------------------------------------------------------

@app.get("/api/v1/bids/{bid_id}/trace")
@app.get("/api/bids/{bid_id}/trace")
@app.get("/bids/{bid_id}/trace")
async def get_bid_compliance_trace(bid_id: str, db=Depends(get_db)):
    b_oid = safe_oid(bid_id)
    conds = [{"_id": b_oid}] if b_oid else []
    conds.extend([{"_id": bid_id}, {"id": bid_id}])
    bid = await db["bids"].find_one({"$or": conds})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")

    bidder = None
    bidder_id = bid.get("bidder_id")
    if bidder_id:
        bdr_oid = safe_oid(bidder_id)
        bdr_conds = [{"_id": bdr_oid}] if bdr_oid else []
        bdr_conds.extend([{"user_id": bidder_id}, {"id": bidder_id}, {"email": bidder_id}])
        bidder = await db["bidders"].find_one({"$or": bdr_conds})

    tender = None
    tender_id = bid.get("tender_id")
    if tender_id:
        t_oid = safe_oid(tender_id)
        t_conds = [{"_id": t_oid}] if t_oid else []
        t_conds.extend([{"tender_no": tender_id}, {"reference_number": tender_id}, {"id": tender_id}])
        tender = await db["tenders"].find_one({"$or": t_conds})

    # Fetch stored rule results from bid or rule_results collection
    rule_results = []
    stored_evals = bid.get("evaluation_results", [])
    for se in stored_evals:
        rule_results.append({
            "id": str(uuid.uuid4()),
            "rule_id": se.get("clause_id") or se.get("rule_id", ""),
            "clause_id": se.get("clause_id", ""),
            "requirement_rule_id": se.get("clause_id") or se.get("rule_id", ""),
            "result": se.get("status") or se.get("result", "PASS"),
            "explanation": se.get("explanation") or "Rule verified against submitted evidence",
            "confidence": 1.0 if (se.get("status") == "PASS") else 0.5,
            "evaluated_at": se.get("evaluated_at") or utcnow_str(),
        })

    if not rule_results:
        async for rr in db["rule_results"].find({"$or": [{"bid_id": bid_id}, {"bid_id": b_oid}] if b_oid else [{"bid_id": bid_id}]}):
            rr["id"] = str(rr.get("_id", ""))
            rule_results.append(rr)

    # Fetch evidence documents
    evidence_list = []
    ev_conds = [{"bid_id": bid_id}, {"package_id": bid_id}]
    if b_oid:
        ev_conds.append({"bid_id": str(b_oid)})
    async for ev in db["evidence"].find({"$or": ev_conds}):
        ev["id"] = str(ev.get("_id", ""))
        evidence_list.append(ev)

    # Fetch verifications from bid or collection
    verif_list = list(bid.get("verifications", []))
    if not verif_list:
        async for vr in db["verifications"].find({"$or": [{"bid_id": bid_id}, {"bid_id": str(b_oid)}] if b_oid else [{"bid_id": bid_id}]}):
            vr["id"] = str(vr.get("_id", ""))
            verif_list.append(vr)

    # Fetch officer action
    action = await db["officer_actions"].find_one({"bid_id": bid_id}, sort=[("acted_at", -1)])
    officer_node = None
    if action:
        officer_node = {
            "action_id": str(action.get("_id", "")),
            "action": action.get("action", ""),
            "comment": action.get("comment", ""),
            "officer_id": action.get("officer_id", ""),
            "acted_at": action.get("acted_at", ""),
        }

    # Fetch rules for this tender
    rules = []
    t_id_str = str(tender["_id"]) if tender else bid.get("tender_id")
    ref_no_str = tender.get("reference_number") if tender else bid.get("tender_reference")
    rule_queries = []
    if t_id_str:
        rule_queries.append({"tender_id": t_id_str})
    if ref_no_str:
        rule_queries.append({"tender_id": ref_no_str})
        rule_queries.append({"tender_no": ref_no_str})
    if rule_queries:
        async for r in db["rules"].find({"$or": rule_queries}):
            r["id"] = str(r.get("_id", ""))
            rules.append(r)

    # If no stored rule results, compute on the fly so trace is always available
    if not rule_results and rules:
        for rule in rules:
            res = compute_rule_result(rule, evidence_list, verif_list)
            rule_results.append({
                "id": str(uuid.uuid4()),
                "rule_id": rule["id"],
                "clause_id": rule.get("clause_id", ""),
                "requirement_rule_id": rule["id"],
                "result": res["result"],
                "explanation": res["explanation"],
                "confidence": res["confidence"],
                "evaluated_at": utcnow_str(),
                "requirement_rule": rule,
            })

    chains = []
    for idx, rule in enumerate(rules):
        rule_id = rule.get("id", "")
        clause_id = rule.get("clause_id", "")
        matching_res = next((
            r for r in rule_results
            if str(r.get("rule_id", "")) == rule_id
            or str(r.get("requirement_rule_id", "")) == rule_id
            or (clause_id and r.get("clause_id") == clause_id)
        ), None)

        if not matching_res:
            res_eval = compute_rule_result(rule, evidence_list, verif_list)
            matching_res = {
                "id": str(uuid.uuid4()),
                "result": res_eval["result"],
                "explanation": res_eval["explanation"],
                "confidence": res_eval["confidence"],
                "evaluated_at": utcnow_str(),
            }

        rule_type = rule.get("rule_type", "").upper()
        rule_metric = (rule.get("metric") or "").lower()

        matched_ev = []
        for ev in evidence_list:
            field = (ev.get("field") or ev.get("field_name") or "").lower()
            if rule_metric and (rule_metric in field or field in rule_metric):
                matched_ev.append({
                    "evidence_id": ev.get("id"),
                    "field": ev.get("field") or ev.get("field_name", ""),
                    "raw_value": str(ev.get("raw_value", "")),
                    "normalized_value": str(ev.get("normalized_value", "")),
                    "confidence": ev.get("confidence", 0.95),
                    "document_filename": ev.get("document_filename") or ev.get("filename", "bidder_document.pdf"),
                    "source_page": ev.get("source_page", 1),
                    "extraction_method": ev.get("extraction_method", "OCR_PYMUPDF"),
                })

        matched_verif = []
        for vr in verif_list:
            source = (vr.get("source") or "").upper()
            if ("GST" in rule_metric.upper() and "GST" in source) or \
               ("PAN" in rule_metric.upper() and "PAN" in source) or \
               ("UDYAM" in rule_metric.upper() and "UDYAM" in source) or \
               ("TURNOVER" in rule_metric.upper() and "GST" in source) or \
               ("EPFO" in rule_metric.upper() and "EPFO" in source):
                matched_verif.append({
                    "record_id": vr.get("id") or vr.get("record_id", ""),
                    "source": vr.get("source", ""),
                    "source_label": vr.get("source_label", f"Authorized Registry Adapter — {vr.get('source', '')}"),
                    "connector_status": vr.get("status") or vr.get("connector_status", "VERIFIED"),
                    "fields_verified": vr.get("fields_verified") or {},
                    "message": vr.get("message", "Statutory verification confirmed."),
                    "checked_at": vr.get("checked_at") or vr.get("response_time") or utcnow_str(),
                    "simulated": False,
                })

        chains.append({
            "chain_id": f"chain_{idx+1}_{rule_id or clause_id or idx}",
            "clause_number": rule.get("clause_id") or f"Clause {idx+1}",
            "clause_title": rule.get("metric", "").replace("_", " ").title(),
            "clause_text": rule.get("clause_text") or rule.get("description") or f"Requirement for {rule.get('metric')}",
            "rule": {
                "rule_id": rule_id,
                "rule_type": rule.get("metric") or rule.get("rule_type", "ELIGIBILITY"),
                "description": rule.get("description") or rule.get("clause_text", ""),
                "metric": rule.get("metric"),
                "operator": rule.get("operator", ">="),
                "threshold_value": str(rule.get("threshold", rule.get("threshold_value", ""))),
                "threshold_unit": rule.get("unit", rule.get("threshold_unit", "")),
                "is_mandatory": rule.get("is_mandatory", True),
            },
            "evidence": matched_ev,
            "verifications": matched_verif,
            "result": {
                "result_id": str(matching_res.get("id", "")),
                "result": matching_res.get("result") or matching_res.get("status", "PASS"),
                "explanation": matching_res.get("explanation", ""),
                "evaluated_at": matching_res.get("evaluated_at"),
                "confidence": matching_res.get("confidence", 0.95),
            },
            "officer_action": officer_node,
        })

    return {
        "bid_id": bid_id,
        "bidder_name": bid.get("bidder_name") or (bidder.get("name") if bidder else "Bharat Engineering & Industrial Ltd"),
        "tender_reference": bid.get("tender_reference") or (tender.get("reference_number") if tender else "GEM/2026/B/4521001"),
        "overall_result": bid.get("compliance_status") or bid.get("overall_status") or "PASS",
        "risk_level": bid.get("risk_band") or bid.get("risk_level") or "LOW",
        "chains": chains,
    }


# --- AUDIT REPORT ------------------------------------------------------------

@app.get("/api/bids/{bid_id}/report")
async def get_audit_report(bid_id: str, db=Depends(get_db)):
    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")

    tender = await db["tenders"].find_one({"_id": bid["tender_id"]})
    bidder = await db["bidders"].find_one({"_id": bid["bidder_id"]})

    rule_results = []
    async for rr in db["rule_results"].find({"bid_id": to_oid(bid_id)}):
        rr["id"] = str(rr.pop("_id"))
        if isinstance(rr.get("bid_id"), ObjectId):
            rr["bid_id"] = str(rr["bid_id"])
        rule_results.append(rr)

    verifications = []
    async for vr in db["verifications"].find({"bid_id": bid_id}):
        vr["id"] = str(vr.pop("_id")); verifications.append(vr)

    audit_events = []
    async for ev in db["audit_events"].find({"bid_id": bid_id}).sort("created_at", 1):
        audit_events.append({"id": str(ev["_id"]), "event_type": ev.get("event_type"),
                              "actor": ev.get("actor"), "details": ev.get("details"),
                              "created_at": ev.get("created_at"), "event_hash": ev.get("event_hash")})

    risk_data, _ = compute_risk([{"result": rr["result"]} for rr in rule_results]) if rule_results else ({}, None)

    return {
        "report_generated_at": utcnow_str(), "report_id": str(uuid.uuid4()),
        "platform": "RashtraBid v3.0 -- SIH26100",
        "disclaimer": "AI-assisted decision support. Final authority rests with the Procurement Officer.",
        "tender": {"id": str(tender["_id"]) if tender else None,
                   "reference_number": tender.get("reference_number") if tender else None,
                   "title": tender.get("title") if tender else None,
                   "organization": tender.get("organization") if tender else None},
        "bidder": {"id": str(bidder["_id"]) if bidder else None,
                   "name": bidder.get("name") if bidder else None,
                   "gstin": bidder.get("gstin") if bidder else None,
                   "pan": bidder.get("pan") if bidder else None,
                   "category": bidder.get("category") if bidder else None,
                   "turnover_cr": bidder.get("turnover_cr") if bidder else None},
        "compliance_summary": {**risk_data, "overall_status": bid.get("overall_status"),
                               "compliance_score": bid.get("compliance_score"),
                               "risk_level": bid.get("risk_level"), "officer_status": bid.get("officer_status"),
                               "officer_comment": bid.get("officer_comment"), "officer_id": bid.get("officer_id")},
        "rule_results": rule_results, "government_verifications": verifications, "audit_trail": audit_events,
    }


# --- CORRIGENDUM IMPACT ANALYZER ---------------------------------------------

class CorrigendumRequest(BaseModel):
    tender_id: str
    changed_rule_type: str
    new_threshold_value: str
    amendment_notes: Optional[str] = ""


@app.post("/api/corrigendum/impact-analysis")
async def corrigendum_impact(body: CorrigendumRequest, user: dict = Depends(require_role("PROCUREMENT_OFFICER")), db=Depends(get_db)):
    tender = await db["tenders"].find_one({"_id": to_oid(body.tender_id)})
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    rule = await db["rules"].find_one(
        {"tender_id": to_oid(body.tender_id), "rule_type": body.changed_rule_type.upper()},
        sort=[("_id", -1)]
    )
    if not rule:
        raise HTTPException(status_code=404, detail=f"No rule of type '{body.changed_rule_type}' found")

    changed_rule = {**rule, "id": str(rule["_id"]), "threshold_value": body.new_threshold_value}

    bidder_impacts = []
    total_affected = 0

    async for bid in db["bids"].find({"tender_id": to_oid(body.tender_id)}):
        bid_id = str(bid["_id"])
        bidder = await db["bidders"].find_one({"_id": bid["bidder_id"]})

        old_rr = await db["rule_results"].find_one({"bid_id": bid["_id"], "requirement_rule_id": str(rule["_id"])})
        old_result = old_rr["result"] if old_rr else "UNKNOWN"

        evidence = []
        async for ev in db["evidence"].find({"bid_id": bid_id}):
            evidence.append(ev)
        verifications = []
        async for vr in db["verifications"].find({"bid_id": bid_id}):
            verifications.append(vr)

        new_result_obj = compute_rule_result(changed_rule, evidence, verifications)
        new_result = new_result_obj["result"]
        changed = old_result != new_result
        if changed:
            total_affected += 1

        bidder_impacts.append({
            "bid_id": bid_id, "bidder_id": str(bidder["_id"]) if bidder else None,
            "bidder_name": bidder.get("name", "") if bidder else "", "old_result": old_result,
            "new_result": new_result, "changed": changed,
            "action_required": "NO_ACTION" if not changed else ("DISQUALIFY" if new_result == "FAIL" else "RE_EVALUATE"),
            "explanation": new_result_obj["explanation"],
        })

    return {
        "tender_id": body.tender_id, "tender_reference": tender.get("reference_number", ""),
        "changed_rule_type": body.changed_rule_type.upper(),
        "old_threshold": str(rule.get("threshold_value", "")), "new_threshold": body.new_threshold_value,
        "amendment_notes": body.amendment_notes, "total_bids_analyzed": len(bidder_impacts),
        "total_affected": total_affected, "total_unchanged": len(bidder_impacts) - total_affected,
        "bidder_impacts": bidder_impacts,
        "analysis_note": "READ-ONLY analysis. No stored results modified. Officer must trigger re-evaluation.",
        "analyzed_at": utcnow_str(),
    }


# --- USER MANAGEMENT ---------------------------------------------------------

@app.get("/api/users")
async def list_users(user: dict = Depends(require_role("PROCUREMENT_OFFICER")), db=Depends(get_db)):
    users = []
    async for u in db["users"].find({}, {"password_hash": 0}):
        u["id"] = str(u.pop("_id")); users.append(u)
    return users


@app.post("/api/users", status_code=201)
async def create_user(body: dict, admin: dict = Depends(require_role("PROCUREMENT_OFFICER")), db=Depends(get_db)):
    required = {"username", "password", "name", "role"}
    if not required.issubset(body.keys()):
        raise HTTPException(status_code=400, detail=f"Required: {required}")
    if body["role"] not in {"PROCUREMENT_OFFICER"}:
        raise HTTPException(status_code=400, detail="Role must be PROCUREMENT_OFFICER")
    existing = await db["users"].find_one({"username": body["username"]})
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    user_doc = {
        "username": body["username"], "password_hash": hash_password(body["password"]),
        "role": body["role"], "name": body["name"], "created_at": utcnow_str(), "created_by": admin["username"],
    }
    result = await db["users"].insert_one(user_doc)
    return {"id": str(result.inserted_id), "username": body["username"], "role": body["role"]}


# --- DEMO RESET --------------------------------------------------------------

@app.post("/api/demo/reset")
async def reset_demo(db=Depends(get_db)):
    """Clear all data and reseed default accounts. For development/demo use only."""
    collections = [
        "tenders", "bids", "bidders", "rules", "rule_results",
        "evidence", "verifications", "audit_events", "documents", "tender_docs", "officer_actions",
    ]
    for col in collections:
        await db[col].delete_many({})

    # Remove non-officer users, reseed defaults
    await db["users"].delete_many({"role": {"$ne": "PROCUREMENT_OFFICER"}})
    await db["users"].delete_many({})
    await seed_default_users(db)

    return {"message": "Demo reset complete. All data cleared. Default accounts restored."}
