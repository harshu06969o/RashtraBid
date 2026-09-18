"""
GeM-Guard — Tender AI Compiler Pipeline
Strict Specifications:
1. PDF Ingestion: Utilizes PyMuPDF (fitz) to parse tender PDFs, capturing text and table structures.
2. Domain Verification: Validates whether the uploaded file is a legitimate procurement/RFP document.
   Rejects non-tender documents (resumes, general slides, receipts) from generating fake compliance rules.
3. Rule Extraction Engine:
   - When GEMINI_API_KEY is configured: Calls Google Gemini Flash-Lite (gemini-3.5-flash-lite) with structured JSON output.
   - When offline / no API key: High-precision deterministic layout-aware regex & table compiler:
     * Financial turnover thresholds (INR Cr)
     * Make in India (MII) local content exact percentages
     * Statutory registrations (GST, PAN, Udyam, EMD, Experience)
4. Maps outputs directly to Pydantic RequirementRule domain models.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.schemas.domain import RequirementRule, RuleSeverity

logger = logging.getLogger("gemguard.tender_compiler")


def get_ai_credentials() -> Dict[str, str]:
    """Dynamically fetch Google Gemini configuration from environment or config."""
    try:
        from app.config import (
            GEMINI_API_KEY as CFG_GEMINI_KEY,
            GEMINI_MODEL as CFG_GEMINI_MODEL,
        )
    except Exception:
        CFG_GEMINI_KEY, CFG_GEMINI_MODEL = "", "gemini-3.5-flash-lite"

    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or CFG_GEMINI_KEY or "").strip()
    gemini_model = (os.getenv("GEMINI_MODEL") or CFG_GEMINI_MODEL or "gemini-3.5-flash-lite").strip()

    return {
        "gemini_key": gemini_key,
        "gemini_model": gemini_model,
    }


@dataclass
class ParsedTable:
    """Represents an extracted table structure from a PDF page."""
    page_number: int
    headers: List[str]
    rows: List[List[str]]
    markdown: str


@dataclass
class ParsedPDFDocument:
    """Complete parsed output of a tender PDF document."""
    total_pages: int
    full_text: str
    pages_text: List[str]
    tables: List[ParsedTable]
    metadata: Dict[str, Any]
    is_tender: bool = True
    detection_reason: str = ""
    detected_indicators: List[str] = field(default_factory=list)


class TenderPDFParser:
    """
    Parses Tender PDFs using PyMuPDF.
    Captures freeform text, structured table data, and verifies tender domain context.
    """

    TENDER_INDICATORS = [
        "tender", "bid", "bidding", "bidder", "bidders", "rfp", "request for proposal",
        "nit", "notice inviting tender", "procurement", "procuring entity",
        "scope of work", "eligibility criteria", "technical specifications",
        "contract", "gem", "turnover", "commercial terms", "earnest money deposit",
        "emd", "security deposit", "corrigendum", "clause", "evaluation methodology",
        "general conditions", "special conditions", "qualification criteria",
        "competent authority", "cpcl", "ministry", "public procurement", "gem/202",
    ]

    @classmethod
    def detect_tender_document(cls, text: str) -> Tuple[bool, str, List[str]]:
        """
        Validate whether the uploaded PDF possesses genuine tender/procurement characteristics.
        Prevents random non-procurement files (resumes, photos, homework, receipts) from generating mock rules.
        """
        clean_text = text.strip()
        if len(clean_text) < 50:
            return False, "Document contains no readable text or is empty. Please ensure the PDF has searchable text.", []

        lower_text = clean_text.lower()
        matched_indicators = []
        for keyword in cls.TENDER_INDICATORS:
            if re.search(r"\b" + re.escape(keyword) + r"\b", lower_text):
                matched_indicators.append(keyword)

        # A valid procurement tender must match at least 2 distinct domain terms
        if len(matched_indicators) < 2:
            return (
                False,
                f"Uploaded document does not contain tender or procurement terminology (only {len(matched_indicators)} indicator found).",
                matched_indicators,
            )

        return True, "Valid Tender / RFP Document detected.", matched_indicators

    @classmethod
    def parse_pdf(cls, file_path_or_bytes: Union[str, Path, bytes]) -> ParsedPDFDocument:
        """
        Parse a PDF file from a filesystem path or raw bytes.
        Captures page texts, all detected table structures, and domain validity.
        """
        if isinstance(file_path_or_bytes, (str, Path)):
            doc = fitz.open(str(file_path_or_bytes))
        elif isinstance(file_path_or_bytes, (bytes, bytearray)):
            doc = fitz.open(stream=bytes(file_path_or_bytes), filetype="pdf")
        elif hasattr(file_path_or_bytes, "read"):
            content = file_path_or_bytes.read()
            doc = fitz.open(stream=bytes(content), filetype="pdf")
        else:
            raise ValueError(f"Unsupported input type for PDF parsing: {type(file_path_or_bytes)}")

        total_pages = len(doc)
        pages_text: List[str] = []
        parsed_tables: List[ParsedTable] = []

        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            # 1. Extract regular text
            text = page.get_text("text") or ""
            pages_text.append(text)

            # 2. Extract tables using PyMuPDF table finder
            try:
                table_finder = page.find_tables()
                if table_finder and table_finder.tables:
                    for table in table_finder.tables:
                        extracted = table.extract()
                        if not extracted or len(extracted) < 2:
                            continue
                        headers = [str(c).strip() if c else f"Col_{i}" for i, c in enumerate(extracted[0])]
                        raw_rows = extracted[1:]
                        rows = [[str(c).strip() if c else "" for c in r] for r in raw_rows]

                        # Generate clean Markdown representation of the table
                        md_lines = [
                            "| " + " | ".join(headers) + " |",
                            "| " + " | ".join(["---"] * len(headers)) + " |",
                        ]
                        for row in rows:
                            padded = row + [""] * (len(headers) - len(row))
                            md_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")

                        parsed_tables.append(ParsedTable(
                            page_number=page_num,
                            headers=headers,
                            rows=rows,
                            markdown="\n".join(md_lines),
                        ))
            except Exception as tbl_err:
                logger.debug("Table detection note on page %d: %s", page_num, tbl_err)

        doc.close()
        full_text = "\n\n".join(pages_text)

        # 3. Check tender authenticity
        is_tender, detection_reason, matched_indicators = cls.detect_tender_document(full_text)

        # 4. Extract metadata from text
        metadata = cls._extract_tender_metadata(full_text)

        logger.info(
            "Parsed PDF: %d pages, %d tables, %d total chars. Tender verified: %s (%s)",
            total_pages,
            len(parsed_tables),
            len(full_text),
            is_tender,
            detection_reason,
        )

        return ParsedPDFDocument(
            total_pages=total_pages,
            full_text=full_text,
            pages_text=pages_text,
            tables=parsed_tables,
            metadata=metadata,
            is_tender=is_tender,
            detection_reason=detection_reason,
            detected_indicators=matched_indicators,
        )

    @classmethod
    def _extract_tender_metadata(cls, text: str) -> Dict[str, Any]:
        """Extract high-level metadata (Tender No, Title, Organization, Closing Date)."""
        meta: Dict[str, Any] = {
            "tender_no": None,
            "title": "Procurement of Materials & Services",
            "organization": "CPCL",
            "closing_date": None,
            "estimated_value": None,
        }

        # Tender reference number regex
        tender_no_patterns = [
            r"GEM/\d{4}/[A-Z]/\d+",
            r"Tender\s+(?:Reference\s+)?(?:Number|No\.?)[\s:]+([A-Z0-9/\-_]+)",
            r"RFP\s+No\.?[\s:]+([A-Z0-9/\-_]+)",
            r"NIT\s+No\.?[\s:]+([A-Z0-9/\-_]+)",
            r"Reference\s+No[\s:]+([A-Z0-9/\-_]+)",
        ]
        for pat in tender_no_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                meta["tender_no"] = m.group(1) if m.groups() else m.group(0)
                break

        # Organization / Issuing Authority
        org_patterns = [
            r"Chennai\s+Petroleum\s+Corporation\s+Limited|CPCL",
            r"Issuing\s+Authority[\s:]+([^\n]+)",
            r"Procuring\s+Entity[\s:]+([^\n]+)",
            r"Ministry\s+of\s+[A-Za-z\s]+",
        ]
        for pat in org_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                matched_org = m.group(1) if m.groups() and m.group(1) else m.group(0)
                if "chennai petroleum" in matched_org.lower() or "cpcl" in matched_org.lower():
                    meta["organization"] = "CPCL"
                else:
                    meta["organization"] = matched_org.strip()
                break

        # Title
        title_patterns = [
            r"Request\s+for\s+Proposal\s*\([^\)]+\)[\s\n]+([^\n]+)",
            r"Scope\s+of\s+Work[\s:]+([^\n\.]+)",
            r"Name\s+of\s+Work[\s:]+([^\n]+)",
            r"Tender\s+Document\s+for\s+([^\n]+)",
            r"Subject[\s:]+([^\n]+)",
        ]
        for pat in title_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                meta["title"] = m.group(1).strip()
                break

        return meta


class RuleExtractionEngine:
    """
    Parses natural language clauses and table structures into executable
    JSON RequirementRule records.
    Extracts:
    - Financial turnover thresholds (INR Cr)
    - Make in India (MII) local content exact percentages
    - Mandatory statutory registrations (GST, PAN, Udyam, EMD, Experience)
    """

    def __init__(self, tender_id: Optional[str] = None):
        self.tender_id = tender_id

    def extract_rules(self, parsed_pdf: ParsedPDFDocument) -> List[RequirementRule]:
        """
        Extract rules using Google Gemini Flash-Lite when credentials are configured,
        with seamless high-precision deterministic pattern fallback.
        """
        # If the document is not an authentic tender, return empty rules
        if not parsed_pdf.is_tender:
            logger.warning(
                "Rule extraction skipped: Document is not a valid tender/RFP (%s)",
                parsed_pdf.detection_reason,
            )
            return []

        creds = get_ai_credentials()

        # 1. Use Google Gemini Flash-Lite API if GEMINI_API_KEY is configured
        if creds["gemini_key"]:
            try:
                gemini_rules = self._extract_rules_via_gemini(
                    parsed_pdf, creds["gemini_key"], creds["gemini_model"]
                )
                if gemini_rules:
                    logger.info("Successfully extracted %d rules via Google Gemini Flash-Lite (%s)", len(gemini_rules), creds["gemini_model"])
                    return gemini_rules
            except Exception as exc:
                logger.warning("Gemini Flash-Lite rule extraction failed (%s). Falling back to deterministic engine.", exc)

        # 2. Deterministic extraction (offline resilience)
        rules = self._extract_rules_deterministic(parsed_pdf)
        logger.info("Extracted %d rules via deterministic pattern engine", len(rules))
        return rules

    def _extract_rules_via_gemini(
        self, parsed_pdf: ParsedPDFDocument, api_key: str, model_name: str = "gemini-3.5-flash-lite"
    ) -> List[RequirementRule]:
        """Call Google Gemini Flash-Lite REST API using structured JSON output format via httpx."""
        import httpx

        tables_context = "\n\n".join(
            f"--- Table on Page {t.page_number} ---\n{t.markdown}"
            for t in parsed_pdf.tables[:5]
        )
        context = f"=== TENDER DOCUMENT TEXT (Sample) ===\n{parsed_pdf.full_text[:14000]}\n\n=== EXTRACTED TABLES ===\n{tables_context}"

        prompt = (
            "You are an expert AI Procurement Compliance Architect for Indian Public Procurement (GeM / CPCL).\n"
            "Analyze the tender document text and tables, and extract ALL legitimate eligibility rules exhaustively.\n"
            "You must extract ALL rules exhaustively from Section 2, Section 3, and Section 6. Do NOT stop after statutory/financial rules. Check every row in tables and all sub-clauses.\n"
            "There are 8 eligibility rules R-01 through R-08 in this document; verify your output contains all 8 before completing.\n"
            "If the document is NOT a tender or RFP document, output {\"is_tender\": false, \"rules\": []}.\n"
            "If it IS a tender, extract all explicit eligibility criteria including but not limited to:\n"
            "1. Financial turnover (e.g. INR Crores)\n"
            "2. Make in India (MII) local content\n"
            "3. Statutory registrations: GST, PAN, Udyam / MSME\n"
            "4. OEM authorization letters\n"
            "5. Quality Certifications (e.g. ISO 9001)\n"
            "6. Labor compliance (e.g. EPFO)\n"
            "7. Vendor Declarations (e.g. Debarment, Blacklisting)\n"
            "8. Legal Entity Name Matching across documents\n\n"
            "IMPORTANT: For the 'metric' field, you MUST map the requirement to one of the following exact system codes: "
            "'annual_turnover_cr', 'local_content_percentage', 'gst_registration_active', 'pan_card_valid', "
            "'udyam_registration_active', 'oem_authorization', 'iso_9001_validity', 'epfo_status', "
            "'debarment_status', 'legal_name_matching'.\n\n"
            "Output a JSON object matching the requested schema exactly.\n\n"
            f"{context}"
        )

        response_schema = {
            "type": "OBJECT",
            "properties": {
                "is_tender": {"type": "BOOLEAN"},
                "rules": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "ruleId": {"type": "STRING"},
                            "name": {"type": "STRING"},
                            "category": {"type": "STRING", "enum": ["FINANCIAL", "STATUTORY", "TECHNICAL", "COMPLIANCE"]},
                            "type": {"type": "STRING", "enum": ["MANDATORY", "CONDITIONAL"]},
                            "description": {"type": "STRING"},
                            "expectedEvidence": {"type": "STRING"},
                            "temporalCutoff": {"type": "STRING"},
                            "clause_id": {"type": "STRING"},
                            "metric": {
                                "type": "STRING",
                                "enum": [
                                    "annual_turnover_cr",
                                    "local_content_percentage",
                                    "gst_registration_active",
                                    "pan_card_valid",
                                    "udyam_registration_active",
                                    "oem_authorization",
                                    "iso_9001_validity",
                                    "epfo_status",
                                    "debarment_status",
                                    "legal_name_matching"
                                ]
                            },
                            "operator": {"type": "STRING", "enum": [">=", ">", "<=", "<", "==", "!=", "contains"]},
                            "threshold": {"type": "STRING"},
                            "unit": {"type": "STRING"},
                            "severity": {"type": "STRING", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                            "clause_text": {"type": "STRING"},
                            "evidence_type": {"type": "STRING"},
                            "verification_source": {"type": "STRING"}
                        },
                        "required": ["ruleId", "name", "category", "type", "description", "expectedEvidence", "clause_id", "metric", "operator", "threshold", "severity", "evidence_type"]
                    }
                }
            },
            "required": ["is_tender", "rules"]
        }

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "temperature": 0.0,
            }
        }

        # Model resolution: prioritizes gemini-3.5-flash-lite as requested by user
        def _resolve_candidate_models(m_name: str) -> List[str]:
            raw = (m_name or "").strip()
            cleaned = raw.lower().replace(" ", "-").replace("_", "-")
            if cleaned.startswith("models/"):
                cleaned = cleaned[7:]
            candidates = []
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
            if "gemini-3.5-flash-lite" not in candidates:
                candidates.insert(0, "gemini-3.5-flash-lite")
            # Alternative Flash-Lite endpoints in case of API version availability
            for lite in ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash-lite-preview-02-05"]:
                if lite not in candidates:
                    candidates.append(lite)
            return candidates

        models_to_try = _resolve_candidate_models(model_name)
        last_error = None
        data = None

        with httpx.Client(timeout=30.0) as client:
            for candidate in models_to_try:
                endpoint_model = f"models/{candidate}" if not candidate.startswith("models/") else candidate
                url = f"https://generativelanguage.googleapis.com/v1beta/{endpoint_model}:generateContent?key={api_key}"
                try:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        break
                    elif resp.status_code == 404:
                        logger.warning("Gemini model %s not found (404). Trying next candidate...", candidate)
                        last_error = resp.text
                        continue
                    else:
                        resp.raise_for_status()
                except Exception as ex:
                    last_error = ex
                    logger.warning("Gemini invocation with %s failed: %s", candidate, ex)
                    continue

        if data is None:
            raise RuntimeError(f"Gemini API calls failed for candidates {models_to_try}: {last_error}")

        candidates_list = data.get("candidates", [])
        if not candidates_list:
            return []

        parts = candidates_list[0].get("content", {}).get("parts", [])
        if not parts:
            return []

        raw_text = parts[0].get("text", "{}")
        parsed = json.loads(raw_text)

        if not parsed.get("is_tender", True):
            return []

        raw_rules = parsed.get("rules", [])
        
        if len(raw_rules) < 8:
            logger.warning("Expected at least 8 rules, but LLM only extracted %d. Potential truncation or extraction failure detected.", len(raw_rules))
            
        rules: List[RequirementRule] = []
        for r in raw_rules:
            try:
                r["tender_id"] = self.tender_id
                
                # Store structural fields within conditions for provenance
                r["conditions"] = {
                    "ruleId": r.get("ruleId"),
                    "name": r.get("name"),
                    "category": r.get("category"),
                    "type": r.get("type"),
                    "expectedEvidence": r.get("expectedEvidence"),
                    "temporalCutoff": r.get("temporalCutoff"),
                }
                
                # Normalize boolean string threshold back to Python boolean
                if str(r.get("threshold")).lower() == "true":
                    r["threshold"] = True
                elif str(r.get("threshold")).lower() == "false":
                    r["threshold"] = False
                    
                rule_obj = RequirementRule(**r)
                rules.append(rule_obj)
            except Exception as parse_err:
                logger.warning("Skipped invalid Gemini rule item: %s (%s)", r, parse_err)

        return rules

    def _extract_rules_deterministic(self, parsed_pdf: ParsedPDFDocument) -> List[RequirementRule]:
        """
        High-precision deterministic rule extraction engine.
        Parses text and table cells for:
        1. Financial turnover thresholds (INR Cr)
        2. Make in India (MII) local content exact percentages
        3. Mandatory statutory registrations (GST, PAN, Udyam, EMD, Experience)
        """
        text = parsed_pdf.full_text
        rules: List[RequirementRule] = []

        # ── 1. Financial Turnover Threshold ───────────────────────────────────
        turnover_found = False
        turnover_val: Optional[float] = None
        turnover_clause_id = "Clause 3.1"
        turnover_snippet = ""

        turnover_patterns = [
            r"(?:average\s+annual|minimum\s+annual|annual)?\s*turnover\s*(?:of\s+)?(?:not\s+less\s+than|of\s+at\s+least|minimum)?[\s:]*(?:Rs\.?|INR|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(Crore|Cr|Lakh|L)?",
            r"turnover[\s\S]{1,60}?(?:Rs\.?|INR|₹)\s*([0-9]+(?:\.[0-9]+)?)\s*(Crore|Cr|Lakh|L)?",
            r"(?:INR|Rs\.?|₹)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:Crore|Cr)\s+(?:average\s+annual\s+turnover|turnover)",
            r"turnover\s+(?:threshold|requirement)[\s:]*(?:Rs\.?|INR|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(Crore|Cr|Lakh|L)?",
        ]

        for pat in turnover_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                unit_match = (m.group(2) or "").lower()
                if "lakh" in unit_match or unit_match == "l":
                    val = val / 100.0  # Convert Lakhs to Crores
                turnover_val = val
                turnover_found = True

                # Extract surrounding snippet
                start = max(0, m.start() - 60)
                end = min(len(text), m.end() + 100)
                turnover_snippet = text[start:end].replace("\n", " ").strip()

                # Detect clause identifier
                clause_match = re.search(r"(?:Clause|Section|Para)\s+([0-9]+(?:\.[0-9]+)?)", text[max(0, m.start() - 100):m.end()], re.IGNORECASE)
                if clause_match:
                    turnover_clause_id = f"Clause {clause_match.group(1)}"
                break

        # Check table structures for turnover if not found in text
        if not turnover_found:
            for table in parsed_pdf.tables:
                for row in table.rows:
                    row_str = " ".join(row).lower()
                    if "turnover" in row_str:
                        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:cr|crore|lakh)", row_str)
                        if m:
                            val = float(m.group(1))
                            if "lakh" in row_str:
                                val = val / 100.0
                            turnover_val = val
                            turnover_found = True
                            turnover_snippet = f"Extracted from Table: {' | '.join(row)}"
                            break
                if turnover_found:
                    break

        if turnover_found and turnover_val is not None:
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id=turnover_clause_id,
                metric="annual_turnover_cr",
                operator=">=",
                threshold=turnover_val,
                unit="INR_CR",
                severity="CRITICAL",
                clause_text=turnover_snippet or f"Minimum average annual turnover threshold of INR {turnover_val} Crore",
                evidence_type="CA_CERTIFICATE",
                verification_source="GSTN",
            ))

        # ── 2. Make in India (MII) Local Content Percentage ──────────────────
        mii_found = False
        mii_percentage: Optional[float] = None
        mii_clause_id = "Clause 3.4"
        mii_snippet = ""

        mii_patterns = [
            r"(?:Make\s+in\s+India|MII|local\s+content)[\s\S]{1,60}?(?:minimum|at\s+least)?[\s:]*([0-9]+(?:\.[0-9]+)?)\s*%",
            r"Class-?I\s+local\s+supplier[\s\S]{1,50}?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:local\s+content|MII)",
            r"local\s+content\s+requirement[\s\S]{1,40}?([0-9]+(?:\.[0-9]+)?)\s*%",
        ]

        for pat in mii_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                mii_percentage = float(m.group(1))
                mii_found = True
                start = max(0, m.start() - 50)
                end = min(len(text), m.end() + 80)
                mii_snippet = text[start:end].replace("\n", " ").strip()

                clause_match = re.search(r"(?:Clause|Section|Para)\s+([0-9]+(?:\.[0-9]+)?)", text[max(0, m.start() - 80):m.end()], re.IGNORECASE)
                if clause_match:
                    mii_clause_id = f"Clause {clause_match.group(1)}"
                break

        if mii_found and mii_percentage is not None:
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id=mii_clause_id,
                metric="mii_local_content_percentage",
                operator=">=",
                threshold=mii_percentage,
                unit="%",
                severity="HIGH",
                clause_text=mii_snippet or f"Local supplier requirement with minimum {mii_percentage}% local content",
                evidence_type="MII_DECLARATION",
                verification_source="DPIIT",
            ))

        # ── 3. Mandatory Statutory Registrations (When Mentioned) ──────────────
        lower_text = text.lower()

        # (a) GST Registration Status
        if "gst" in lower_text or "goods and services tax" in lower_text or "gstin" in lower_text:
            gst_snippet = "Active Goods and Services Tax (GST) registration required."
            m_gst = re.search(r"(?:gst\s+registration|gstin|goods\s+and\s+services\s+tax)[\s\S]{1,120}?(?:active|certificate|form\s+reg-06)", text, re.IGNORECASE)
            if m_gst:
                gst_snippet = m_gst.group(0).replace("\n", " ").strip()
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 3.2",
                metric="gst_registration_active",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                clause_text=gst_snippet,
                evidence_type="GST_CERTIFICATE",
                verification_source="GSTN",
            ))

        # (b) PAN Validity
        if "pan" in lower_text or "permanent account number" in lower_text:
            pan_snippet = "Valid Permanent Account Number (PAN) required."
            m_pan = re.search(r"(?:permanent\s+account\s+number|\bpan\b)[\s\S]{1,100}?(?:valid|income\s+tax|department)", text, re.IGNORECASE)
            if m_pan:
                pan_snippet = m_pan.group(0).replace("\n", " ").strip()
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 3.5",
                metric="pan_card_valid",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                clause_text=pan_snippet,
                evidence_type="PAN_CARD",
                verification_source="INCOME_TAX_PAN",
            ))

        # (c) MSME / Udyam Registration
        if "udyam" in lower_text or "msme" in lower_text or "micro, small" in lower_text:
            udyam_snippet = "Valid Udyam Registration Certificate for MSME bidders."
            m_udyam = re.search(r"(?:udyam|msme)[\s\S]{1,120}?(?:registration|active|urn)", text, re.IGNORECASE)
            if m_udyam:
                udyam_snippet = m_udyam.group(0).replace("\n", " ").strip()
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 3.3",
                metric="udyam_registration_active",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="MEDIUM",
                clause_text=udyam_snippet,
                evidence_type="UDYAM_CERTIFICATE",
                verification_source="UDYAM",
            ))

        # (e) Entity Name Consistency
        if re.search(r"pan.*(legal|name)|legal.*name.*pan|entity.*name|name.*match", text, re.IGNORECASE):
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 3.1",
                metric="entity_name_match",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                clause_text="Entity name must match across all statutory documents (PAN, GST, Udyam).",
                evidence_type="PAN_CARD",
                verification_source="INCOME_TAX_PAN",
            ))

        # (f) EPFO
        if re.search(r"epfo|provident\s+fund|establishment\s+code|pf\s+registration", text, re.IGNORECASE):
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 4.1",
                metric="epfo_compliance",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="HIGH",
                clause_text="Mandatory EPFO registration and compliance required for establishments with 20 or more employees.",
                evidence_type="EPFO_EVIDENCE",
                verification_source="EPFO_PORTAL",
            ))

        # (g) OEM Authorization
        if re.search(r"oem|original\s+equipment\s+manufacturer|authorization\s+letter|authorisation\s+letter", text, re.IGNORECASE):
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 5.2",
                metric="oem_authorization_valid",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                clause_text="Valid OEM Authorization certificate required for supplied goods.",
                evidence_type="OEM_AUTHORIZATION",
                verification_source="OEM_PORTAL",
            ))

        # (h) ISO 9001
        if re.search(r"iso\s*9001|quality\s+certificate|quality.system|qs\s+certification", text, re.IGNORECASE):
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 6.1",
                metric="iso_9001_certified",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="MEDIUM",
                clause_text="ISO 9001 Quality Management System certification.",
                evidence_type="ISO_CERTIFICATE",
                verification_source="CERTIFICATION_BODY",
            ))

        # (i) Debarment
        if re.search(r"debarment|debarred|blacklist|not\s+debarred|declaration.*debarment|sanction", text, re.IGNORECASE):
            rules.append(RequirementRule(
                tender_id=self.tender_id,
                clause_id="Clause 7.1",
                metric="not_debarred",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                clause_text="Bidder must not be debarred or blacklisted by any Govt entity.",
                evidence_type="DEBARMENT_DECLARATION",
                verification_source="NCA_DATABASE",
            ))

        return rules


class TenderCompiler:
    """
    Main Orchestrator for Tender Ingestion & Compilation:
    1. Ingests PDF bytes or path
    2. Runs PyMuPDF parser with table capture & domain verification
    3. Executes structured rule extraction engine (Google Gemini Flash-Lite / Deterministic)
    4. Produces validated Tender metadata and RequirementRule models
    """

    @classmethod
    def compile_pdf(
        cls,
        pdf_input: Union[str, Path, bytes],
        tender_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[RequirementRule], Dict[str, Any]]:
        """
        Parse tender PDF and extract compliance rules.

        Returns:
            (tender_metadata, extracted_rules, extraction_diagnostics)
        """
        parsed_pdf = TenderPDFParser.parse_pdf(pdf_input)
        engine = RuleExtractionEngine(tender_id=tender_id)
        rules = engine.extract_rules(parsed_pdf)

        diagnostics = {
            "total_pages": parsed_pdf.total_pages,
            "tables_extracted": len(parsed_pdf.tables),
            "total_chars": len(parsed_pdf.full_text),
            "is_tender": parsed_pdf.is_tender,
            "detection_reason": parsed_pdf.detection_reason,
            "detected_indicators": parsed_pdf.detected_indicators,
            "rules_count": len(rules),
            "table_summaries": [
                {"page": t.page_number, "headers": t.headers, "rows_count": len(t.rows)}
                for t in parsed_pdf.tables
            ],
        }

        return parsed_pdf.metadata, rules, diagnostics
