"""
Requirement Compiler Service.

Transforms tender document text into structured CompiledRule objects.

Architecture
------------
  RequirementCompilerService.compile(source, text) → List[CompiledRule]

  Sources
  -------
  DEMO    — returns hardcoded canonical rules for GEM/2026/B/4521001.
            Works without any uploaded document.
  PATTERN — deterministic regex/heuristic extraction on uploaded PDF text.
  LLM     — (not implemented) abstraction reserved for future AI integration.

CRITICAL
--------
  The compiler only EXTRACTS and STRUCTURES requirements.
  It does NOT produce compliance results (PASS/FAIL/REVIEW/PENDING).
  Compliance status is determined exclusively by the compliance engine
  (Stage 3) using deterministic rule functions.
"""

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from app.services.compiled_rule import CompiledRule, validate_compiled_rule

logger = logging.getLogger("gemguard.compiler")


# ── Demo rules — canonical for GEM/2026/B/4521001 ─────────────────────────────

DEMO_RULES: List[CompiledRule] = [
    CompiledRule(
        requirement_id="REQ-001",
        clause_ref="3.1",
        clause_title="Financial Eligibility",
        clause_text=(
            "The bidder must have an average annual turnover of not less than "
            "\u20b910 Crore (Rupees Ten Crore) during the last three financial years "
            "(FY\u00a02022\u201323, FY\u00a02023\u201324, FY\u00a02024\u201325), "
            "as certified by a Chartered Accountant."
        ),
        source_page=7,
        category="FINANCIAL",
        severity="CRITICAL",
        is_mandatory=True,
        applicability="ALL",
        rule_type="TURNOVER",
        metric="annual_turnover_avg_3fy",
        operator="GTE",
        threshold="10.0",
        unit="INR_CR",
        time_period="LAST_3_FY",
        evidence_type="CA_CERTIFICATE",
        verification_sources=["DOCUMENT", "CA_CERT"],
    ),
    CompiledRule(
        requirement_id="REQ-002",
        clause_ref="3.2",
        clause_title="GST Registration",
        clause_text=(
            "The bidder shall be registered under GST and the registration status "
            "must be ACTIVE as of the date of bid submission."
        ),
        source_page=8,
        category="REGULATORY",
        severity="CRITICAL",
        is_mandatory=True,
        applicability="ALL",
        rule_type="GST_STATUS",
        metric="gst_registration_status",
        operator="ACTIVE",
        threshold="ACTIVE",
        unit="STRING",
        time_period="CURRENT",
        evidence_type="GST_CERTIFICATE",
        verification_sources=["GST_MOCK"],
    ),
    CompiledRule(
        requirement_id="REQ-003",
        clause_ref="3.3",
        clause_title="MSME / Udyam Registration",
        clause_text=(
            "MSME bidders must hold a valid Udyam Registration Certificate. "
            "Large enterprises are exempt from this requirement."
        ),
        source_page=8,
        category="REGULATORY",
        severity="MEDIUM",
        is_mandatory=False,
        applicability="MSME",
        rule_type="UDYAM",
        metric="udyam_registration_status",
        operator="ACTIVE",
        threshold="ACTIVE",
        unit="STRING",
        time_period="CURRENT",
        evidence_type="UDYAM_CERTIFICATE",
        verification_sources=["UDYAM_MOCK"],
    ),
    CompiledRule(
        requirement_id="REQ-004",
        clause_ref="3.4",
        clause_title="Certificate Validity",
        clause_text=(
            "All statutory certificates submitted must be valid as on the bid submission date. "
            "Expired certificates will not be accepted and will be treated as non-compliant."
        ),
        source_page=9,
        category="LEGAL",
        severity="HIGH",
        is_mandatory=True,
        applicability="ALL",
        rule_type="CERT_VALIDITY",
        metric="certificate_expiry_date",
        operator="VALID",
        threshold="VALID",
        unit="BOOL",
        time_period="CURRENT",
        evidence_type="ANY_STATUTORY_CERT",
        verification_sources=["DOCUMENT"],
    ),
    CompiledRule(
        requirement_id="REQ-005",
        clause_ref="3.5",
        clause_title="Entity Name Consistency",
        clause_text=(
            "The legal entity name must be consistent across all submitted documents "
            "(incorporation certificate, GST registration, bid form). "
            "Inconsistencies require clarification before evaluation proceeds."
        ),
        source_page=10,
        category="LEGAL",
        severity="HIGH",
        is_mandatory=True,
        applicability="ALL",
        rule_type="NAME_MATCH",
        metric="legal_entity_name_consistency",
        operator="MATCH",
        threshold="MATCH",
        unit="STRING",
        time_period=None,
        evidence_type="ALL_SUBMITTED_DOCS",
        verification_sources=["MCA_MOCK", "DOCUMENT"],
    ),
]


# ── Pattern Compiler — deterministic regex extraction ──────────────────────────

class PatternCompiler:
    """
    Heuristic compiler using regex patterns on tender document text.

    This is NOT an AI.  It uses deterministic pattern matching.
    Falls back to DEMO rules when patterns yield no results.
    """

    _TURNOVER_RE = re.compile(
        r"(?:average\s+annual\s+turnover|annual\s+turnover)\s*"
        r"(?:of\s+)?(?:not\s+less\s+than\s+)?"
        r"(?:\u20b9|inr|rs\.?|rupees)?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:crore|cr\.?)",
        re.IGNORECASE,
    )
    _GST_RE = re.compile(
        r"(?:gst|goods\s+and\s+services\s+tax)\s+(?:registration|registered).*?"
        r"(?:active|valid|current)",
        re.IGNORECASE | re.DOTALL,
    )
    _UDYAM_RE = re.compile(
        r"udyam\s+(?:registration|certificate|registered)",
        re.IGNORECASE,
    )
    _CERT_RE = re.compile(
        r"(?:certificate|certificates)\s+(?:must\s+be\s+)?(?:valid|not\s+expired)",
        re.IGNORECASE,
    )

    def compile(self, text: str) -> List[CompiledRule]:
        rules: List[CompiledRule] = []

        m = self._TURNOVER_RE.search(text)
        if m:
            threshold = m.group(1)
            ctx = text[max(0, m.start() - 50): m.end() + 200].strip()
            rules.append(CompiledRule(
                requirement_id="REQ-001",
                clause_ref="3.1",
                clause_title="Financial Eligibility",
                clause_text=ctx,
                source_page=None,
                category="FINANCIAL",
                severity="CRITICAL",
                is_mandatory=True,
                applicability="ALL",
                rule_type="TURNOVER",
                metric="annual_turnover_avg_3fy",
                operator="GTE",
                threshold=threshold,
                unit="INR_CR",
                time_period="LAST_3_FY",
                evidence_type="CA_CERTIFICATE",
                verification_sources=["DOCUMENT", "CA_CERT"],
            ))

        if self._GST_RE.search(text):
            idx = len(rules) + 1
            rules.append(CompiledRule(
                requirement_id=f"REQ-{idx:03d}",
                clause_ref="3.2",
                clause_title="GST Registration",
                clause_text="GST registration must be ACTIVE (extracted by pattern).",
                source_page=None,
                category="REGULATORY",
                severity="CRITICAL",
                is_mandatory=True,
                applicability="ALL",
                rule_type="GST_STATUS",
                metric="gst_registration_status",
                operator="ACTIVE",
                threshold="ACTIVE",
                unit="STRING",
                time_period="CURRENT",
                evidence_type="GST_CERTIFICATE",
                verification_sources=["GST_MOCK"],
            ))

        if self._UDYAM_RE.search(text):
            idx = len(rules) + 1
            rules.append(CompiledRule(
                requirement_id=f"REQ-{idx:03d}",
                clause_ref="3.3",
                clause_title="MSME / Udyam Registration",
                clause_text="Valid Udyam Registration required for MSME bidders (extracted).",
                source_page=None,
                category="REGULATORY",
                severity="MEDIUM",
                is_mandatory=False,
                applicability="MSME",
                rule_type="UDYAM",
                metric="udyam_registration_status",
                operator="ACTIVE",
                threshold="ACTIVE",
                unit="STRING",
                time_period="CURRENT",
                evidence_type="UDYAM_CERTIFICATE",
                verification_sources=["UDYAM_MOCK"],
            ))

        if self._CERT_RE.search(text):
            idx = len(rules) + 1
            rules.append(CompiledRule(
                requirement_id=f"REQ-{idx:03d}",
                clause_ref="3.4",
                clause_title="Certificate Validity",
                clause_text="All statutory certificates must be valid on bid date (extracted).",
                source_page=None,
                category="LEGAL",
                severity="HIGH",
                is_mandatory=True,
                applicability="ALL",
                rule_type="CERT_VALIDITY",
                metric="certificate_expiry_date",
                operator="VALID",
                threshold="VALID",
                unit="BOOL",
                time_period="CURRENT",
                evidence_type="ANY_STATUTORY_CERT",
                verification_sources=["DOCUMENT"],
            ))

        if not rules:
            logger.warning("Pattern extraction found no rules — falling back to DEMO rules.")
            return list(DEMO_RULES)

        return rules


# ── Compiler Service ──────────────────────────────────────────────────────────

class RequirementCompilerService:
    """
    Orchestrates requirement compilation.

    Public API
    ----------
    compile(source, text) → List[CompiledRule]
    compile_to_db(db, tender_id, source, text, clauses) → List[RequirementRule ORM]
    """

    def __init__(self):
        self._pattern = PatternCompiler()

    def compile(
        self,
        source: str = "DEMO",
        text: Optional[str] = None,
    ) -> List[CompiledRule]:
        """
        Compile requirements.

        Parameters
        ----------
        source : "DEMO" | "PATTERN"
        text   : PDF-extracted text (required for PATTERN)

        Returns
        -------
        List of validated CompiledRule objects.
        Raises ValueError if any rule fails validation.
        """
        source = source.upper()

        if source == "DEMO":
            raw = list(DEMO_RULES)
        elif source == "PATTERN":
            if not text:
                logger.warning("PATTERN requested but no text supplied — using DEMO.")
                raw = list(DEMO_RULES)
            else:
                raw = self._pattern.compile(text)
        elif source == "LLM":
            raise NotImplementedError(
                "LLM compiler is not implemented in this stage. Use DEMO or PATTERN."
            )
        else:
            raise ValueError(f"Unknown source '{source}'. Use DEMO or PATTERN.")

        validated: List[CompiledRule] = []
        for rule in raw:
            errors = validate_compiled_rule(rule)
            if errors:
                raise ValueError(
                    f"Rule {rule.requirement_id} failed validation: {errors}"
                )
            validated.append(rule)

        logger.info(
            "Compiled %d requirement rules (source=%s)", len(validated), source
        )
        return validated

    def compile_to_db(
        self,
        db,
        tender_id: int,
        source: str = "DEMO",
        text: Optional[str] = None,
        clauses=None,
    ) -> list:
        """
        Compile requirements and persist them to the database.

        Deletes all existing RequirementRules for this tender first,
        then creates new ones from the compiled rules.

        Returns list of RequirementRule ORM objects.
        """
        from app import models

        compiled = self.compile(source=source, text=text)

        # Replace existing rules
        db.query(models.RequirementRule).filter(
            models.RequirementRule.tender_id == tender_id
        ).delete()

        db_rules = []
        clause_map = {c.clause_number: c.id for c in (clauses or [])}

        for rule in compiled:
            db_rule = models.RequirementRule(
                tender_id=tender_id,
                clause_id=clause_map.get(rule.clause_ref),
                requirement_id=rule.requirement_id,
                rule_type=rule.rule_type,
                description=f"{rule.clause_title}: {rule.clause_text[:200]}",
                category=rule.category,
                severity=rule.severity,
                applicability=rule.applicability,
                metric=rule.metric,
                operator=rule.operator,
                threshold_value=rule.threshold,
                threshold_unit=rule.unit,
                time_period=rule.time_period,
                evidence_type=rule.evidence_type,
                verification_sources=rule.verification_sources,
                is_mandatory=rule.is_mandatory,
                compilation_source=source,
                compiled_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(db_rule)
            db_rules.append(db_rule)

        db.flush()
        return db_rules


# Singleton instance
compiler_service = RequirementCompilerService()
