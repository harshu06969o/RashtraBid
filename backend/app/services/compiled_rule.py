"""
CompiledRule — structured output of the RequirementCompiler.

This is an intermediate data object.  The compiler reads tender documents and
produces these.  The compliance engine (Stage 3) evaluates them against
bidder data.  AI NEVER sets compliance status.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CompiledRule:
    """
    A fully-structured compliance requirement extracted from a tender document.

    Fields
    ------
    requirement_id  : Human-readable identifier, e.g. "REQ-001"
    clause_ref      : Clause number in the tender, e.g. "3.1"
    clause_title    : Heading of the clause
    clause_text     : Full verbatim text of the clause
    source_page     : Page number in the source PDF (1-indexed), or None
    category        : FINANCIAL | REGULATORY | TECHNICAL | LEGAL
    severity        : CRITICAL | HIGH | MEDIUM | LOW
    is_mandatory    : True → non-compliance is disqualifying
    applicability   : ALL | MSME | LARGE | STARTUP
    rule_type       : Engine token: TURNOVER | GST_STATUS | UDYAM | CERT_VALIDITY | NAME_MATCH
    metric          : Machine-readable metric name
    operator        : GTE | LTE | EQ | NEQ | ACTIVE | VALID | MATCH | CONTAINS
    threshold       : Threshold value as string
    unit            : INR_CR | BOOL | DATE | STRING
    time_period     : LAST_3_FY | CURRENT | None
    evidence_type   : Expected evidence document type
    verification_sources : List of adapter names the engine will query
    """

    requirement_id: str
    clause_ref: str
    clause_title: str
    clause_text: str
    source_page: Optional[int]

    category: str        # FINANCIAL | REGULATORY | TECHNICAL | LEGAL
    severity: str        # CRITICAL | HIGH | MEDIUM | LOW
    is_mandatory: bool
    applicability: str   # ALL | MSME | LARGE | STARTUP

    rule_type: str       # TURNOVER | GST_STATUS | UDYAM | CERT_VALIDITY | NAME_MATCH
    metric: str
    operator: str        # GTE | LTE | EQ | NEQ | ACTIVE | VALID | MATCH | CONTAINS
    threshold: str
    unit: str            # INR_CR | BOOL | DATE | STRING
    time_period: Optional[str]

    evidence_type: str
    verification_sources: List[str] = field(default_factory=list)


# ── Validation ────────────────────────────────────────────────────────────────

_VALID_CATEGORIES    = {"FINANCIAL", "REGULATORY", "TECHNICAL", "LEGAL"}
_VALID_SEVERITIES    = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
_VALID_OPERATORS     = {"GTE", "LTE", "EQ", "NEQ", "ACTIVE", "VALID", "MATCH", "CONTAINS"}
_VALID_APPLICABILITY = {"ALL", "MSME", "LARGE", "STARTUP"}
_VALID_UNITS         = {"INR_CR", "BOOL", "DATE", "STRING", "PERCENT", "YEARS"}


def validate_compiled_rule(rule: CompiledRule) -> List[str]:
    """
    Validate a CompiledRule.  Returns a list of error strings.
    An empty list means the rule is valid.
    """
    errors: List[str] = []

    # Required non-empty strings
    required = [
        ("requirement_id", rule.requirement_id),
        ("clause_ref",     rule.clause_ref),
        ("clause_text",    rule.clause_text),
        ("category",       rule.category),
        ("severity",       rule.severity),
        ("rule_type",      rule.rule_type),
        ("metric",         rule.metric),
        ("operator",       rule.operator),
        ("threshold",      rule.threshold),
        ("unit",           rule.unit),
        ("evidence_type",  rule.evidence_type),
        ("applicability",  rule.applicability),
    ]
    for fname, val in required:
        if not val or not str(val).strip():
            errors.append(f"Missing required field: {fname}")

    if rule.category not in _VALID_CATEGORIES:
        errors.append(f"Invalid category '{rule.category}'. Must be one of {_VALID_CATEGORIES}")
    if rule.severity not in _VALID_SEVERITIES:
        errors.append(f"Invalid severity '{rule.severity}'. Must be one of {_VALID_SEVERITIES}")
    if rule.operator not in _VALID_OPERATORS:
        errors.append(f"Invalid operator '{rule.operator}'. Must be one of {_VALID_OPERATORS}")
    if rule.applicability not in _VALID_APPLICABILITY:
        errors.append(f"Invalid applicability '{rule.applicability}'. Must be one of {_VALID_APPLICABILITY}")

    return errors
