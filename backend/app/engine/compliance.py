"""
GeM-Guard — Deterministic Compliance Engine & Cross-Document Integrity
Strict Specifications:
1. Deterministic Logic: Evaluate extracted Evidence against compiled RequirementRule thresholds,
   assigning states (PASS, FAIL, REVIEW, PENDING).
2. Cross-Document Integrity (Pandas): Aggregate bid data into Pandas DataFrames.
   Flag contradictions (e.g. PAN vs Udyam legal name mismatch, or CA Cert vs Affidavit turnover discrepancy).
   Set rule status to REVIEW for mismatches.
3. Risk Score: Calculate a Readiness Score (0-100) and assign Risk Bands (LOW, MEDIUM, HIGH, CRITICAL)
   based on mandatory rule satisfaction and evidence completeness.
"""

import difflib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from pydantic import BaseModel, Field

from app.schemas.domain import Evidence, RequirementRule, RuleResult, RuleSeverity, RuleStatus

logger = logging.getLogger("gemguard.engine.compliance")


def utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class IntegrityFinding:
    """Represents a cross-document discrepancy or contradiction detected by Pandas."""
    check_type: str  # NAME_MISMATCH, TURNOVER_DISCREPANCY, PAN_GSTIN_MISMATCH, STATE_CODE_MISMATCH
    severity: str    # CRITICAL, HIGH, MEDIUM, LOW
    field: str
    documents_involved: List[str]
    discrepancy_details: str
    values_found: Dict[str, Any]
    detected_at: str = field(default_factory=utcnow_str)


class ComplianceEvaluationReport(BaseModel):
    """Unified evaluation output produced by the Compliance Engine."""
    bid_id: str
    readiness_score: float = Field(..., ge=0.0, le=100.0, description="Readiness Score 0-100")
    risk_band: RiskBand = Field(..., description="Risk Band: LOW, MEDIUM, HIGH, CRITICAL")
    overall_status: str = Field(..., description="COMPLIANT, PARTIALLY_COMPLIANT, NON_COMPLIANT, PENDING_VERIFICATION, UNDER_REVIEW")
    rule_results: List[Dict[str, Any]]
    integrity_findings: List[Dict[str, Any]]
    evidence_completeness_ratio: float
    mandatory_pass_ratio: float
    evaluated_at: str = Field(default_factory=utcnow_str)
    summary: str


# ── 1. Pandas-Driven Cross-Document Integrity Validator ───────────────────────

class CrossDocumentValidator:
    """
    Pandas-based Cross-Document Integrity Analyzer:
    Ingests all bid evidence into a unified DataFrame and executes cross-document
    consistency validations, flagging contradictions and setting corresponding rules to REVIEW.
    """

    @classmethod
    def create_evidence_dataframe(cls, evidence_list: List[Union[Evidence, Dict[str, Any]]]) -> pd.DataFrame:
        """Converts raw evidence models/dicts into a structured Pandas DataFrame."""
        records = []
        for ev in evidence_list:
            if isinstance(ev, Evidence):
                d = ev.model_dump(by_alias=True)
            elif isinstance(ev, dict):
                d = dict(ev)
            else:
                continue

            raw_dt = str(d.get("doc_type") or d.get("document_type") or "").strip()
            if not raw_dt or raw_dt == "UNKNOWN":
                doc_id_lower = str(d.get("document_id") or "").lower()
                if "pan" in doc_id_lower:
                    raw_dt = "PAN_CARD"
                elif "udyam" in doc_id_lower:
                    raw_dt = "UDYAM_CERTIFICATE"
                elif "gst" in doc_id_lower:
                    raw_dt = "GST_CERTIFICATE"
                elif "ca" in doc_id_lower:
                    raw_dt = "CA_CERTIFICATE"
                elif "affidavit" in doc_id_lower:
                    raw_dt = "FINANCIAL_AFFIDAVIT"
                elif "mii" in doc_id_lower or "declaration" in doc_id_lower:
                    raw_dt = "MII_DECLARATION"
                else:
                    raw_dt = "UNKNOWN"

            records.append({
                "evidence_id": str(d.get("id") or d.get("_id") or ""),
                "document_id": str(d.get("document_id") or ""),
                "package_id": str(d.get("package_id") or d.get("bid_id") or ""),
                "doc_type": raw_dt,
                "field_name": str(d.get("field_name") or ""),
                "normalized_value": d.get("normalized_value"),
                "raw_value": str(d.get("raw_value") or ""),
                "confidence": float(d.get("confidence") or 0.85),
                "page_number": int(d.get("page_number") or 1),
            })

        if not records:
            return pd.DataFrame(columns=[
                "evidence_id", "document_id", "package_id", "doc_type",
                "field_name", "normalized_value", "raw_value", "confidence", "page_number",
            ])

        return pd.DataFrame(records)

    @classmethod
    def clean_name(cls, name_str: str) -> str:
        """Normalize legal company name for robust fuzzy and token comparison."""
        cleaned = re.sub(r"[^\w\s]", " ", str(name_str).upper())
        # Remove common business suffixes to isolate core entity name
        tokens = cleaned.split()
        drop_tokens = {"PVT", "LTD", "LIMITED", "PRIVATE", "LLP", "LLC", "INC", "CORP", "CORPORATION", "M/S", "MESSRS"}
        filtered = [t for t in tokens if t not in drop_tokens]
        return " ".join(filtered).strip()

    @classmethod
    def validate_integrity(cls, df: pd.DataFrame) -> List[IntegrityFinding]:
        """Runs multi-point cross-document integrity checks over the evidence DataFrame."""
        findings: List[IntegrityFinding] = []

        if df.empty:
            return findings

        # ── A. Entity Legal Name Uniformity Check ─────────────────────────────
        name_mask = df["field_name"].isin(["legal_entity_name", "bidder_name", "legal_name"])
        df_names = df[name_mask]

        if len(df_names) >= 2:
            names_by_doc = df_names[["doc_type", "document_id", "normalized_value", "raw_value"]].drop_duplicates()
            name_records = names_by_doc.to_dict(orient="records")

            base_rec = name_records[0]
            base_clean = cls.clean_name(base_rec["normalized_value"] or base_rec["raw_value"])

            for other_rec in name_records[1:]:
                other_clean = cls.clean_name(other_rec["normalized_value"] or other_rec["raw_value"])
                ratio = difflib.SequenceMatcher(None, base_clean, other_clean).ratio()

                # If token overlap / similarity is low (< 0.70), flag as contradiction!
                if ratio < 0.70:
                    findings.append(IntegrityFinding(
                        check_type="NAME_MISMATCH",
                        severity="HIGH",
                        field="legal_entity_name",
                        documents_involved=[base_rec["doc_type"], other_rec["doc_type"]],
                        discrepancy_details=(
                            f"Entity name mismatch between {base_rec['doc_type']} ('{base_rec['normalized_value']}') "
                            f"and {other_rec['doc_type']} ('{other_rec['normalized_value']}'). Similarity: {ratio:.0%}. "
                            f"Possible surrogate bidding or entity inconsistency."
                        ),
                        values_found={
                            base_rec["doc_type"]: base_rec["normalized_value"],
                            other_rec["doc_type"]: other_rec["normalized_value"],
                            "similarity_ratio": round(ratio, 2),
                        },
                    ))

        # ── B. Turnover Discrepancy Check (>5% variance) ──────────────────────
        turn_mask = df["field_name"].isin(["annual_turnover_cr", "turnover_avg_3fy", "turnover"])
        df_turnover = df[turn_mask]

        if len(df_turnover) >= 2:
            turn_values = []
            for _, row in df_turnover.iterrows():
                try:
                    v = float(row["normalized_value"])
                    turn_values.append((row["doc_type"], v, row["evidence_id"]))
                except (ValueError, TypeError):
                    continue

            if len(turn_values) >= 2:
                # Compare max vs min turnover
                min_item = min(turn_values, key=lambda x: x[1])
                max_item = max(turn_values, key=lambda x: x[1])

                if min_item[1] > 0:
                    pct_diff = ((max_item[1] - min_item[1]) / min_item[1]) * 100.0
                    if pct_diff > 5.0:
                        findings.append(IntegrityFinding(
                            check_type="TURNOVER_DISCREPANCY",
                            severity="HIGH",
                            field="annual_turnover_cr",
                            documents_involved=[min_item[0], max_item[0]],
                            discrepancy_details=(
                                f"Financial turnover discrepancy of {pct_diff:.1f}% (>5% threshold) detected between "
                                f"{min_item[0]} (Rs. {min_item[1]:.2f} Cr) and {max_item[0]} (Rs. {max_item[1]:.2f} Cr)."
                            ),
                            values_found={
                                min_item[0]: min_item[1],
                                max_item[0]: max_item[1],
                                "percentage_difference": round(pct_diff, 2),
                            },
                        ))

        # ── C. PAN embedded inside GSTIN Cross-Linkage ────────────────────────
        gstin_rows = df[df["field_name"] == "gstin"]
        pan_rows = df[df["field_name"] == "pan"]

        if not gstin_rows.empty and not pan_rows.empty:
            gstin_val = str(gstin_rows.iloc[0]["normalized_value"]).strip().upper()
            pan_val = str(pan_rows.iloc[0]["normalized_value"]).strip().upper()

            if len(gstin_val) == 15 and len(pan_val) == 10:
                embedded_pan = gstin_val[2:12]
                if embedded_pan != pan_val:
                    findings.append(IntegrityFinding(
                        check_type="PAN_GSTIN_MISMATCH",
                        severity="CRITICAL",
                        field="pan",
                        documents_involved=["GST_CERTIFICATE", "PAN_CARD"],
                        discrepancy_details=(
                            f"Statutory PAN embedded inside GSTIN ('{embedded_pan}') does not match "
                            f"the submitted PAN Card ('{pan_val}'). Possible fraud or disparate entity credentials."
                        ),
                        values_found={
                            "gstin": gstin_val,
                            "embedded_pan": embedded_pan,
                            "submitted_pan": pan_val,
                        },
                    ))

        # ── D. Udyam vs GSTIN State Code Consistency ──────────────────────────
        udyam_rows = df[df["field_name"] == "udyam_number"]
        if not gstin_rows.empty and not udyam_rows.empty:
            gstin_val = str(gstin_rows.iloc[0]["normalized_value"]).strip().upper()
            udyam_val = str(udyam_rows.iloc[0]["normalized_value"]).strip().upper()

            m = re.search(r"UDYAM-([A-Z]{2})-", udyam_val)
            if m and len(gstin_val) >= 2:
                udyam_state = m.group(1)
                gst_state_prefix = gstin_val[:2]
                # Check for major state code mismatches
                # E.g. Tamil Nadu is 33/TN, Maharashtra is 27/MH, Delhi is 07/DL
                state_code_map = {
                    "07": "DL", "27": "MH", "29": "KA", "33": "TN", "06": "HR", "09": "UP", "24": "GJ", "19": "WB",
                }
                expected_state = state_code_map.get(gst_state_prefix)
                if expected_state and expected_state != udyam_state:
                    findings.append(IntegrityFinding(
                        check_type="STATE_CODE_MISMATCH",
                        severity="MEDIUM",
                        field="udyam_number",
                        documents_involved=["GST_CERTIFICATE", "UDYAM_CERTIFICATE"],
                        discrepancy_details=(
                            f"GSTIN state prefix '{gst_state_prefix}' ({expected_state}) differs from "
                            f"Udyam registration state '{udyam_state}'. Multi-state operations require officer review."
                        ),
                        values_found={
                            "gstin_state_code": gst_state_prefix,
                            "expected_state": expected_state,
                            "udyam_state": udyam_state,
                        },
                    ))

        return findings


# ── 2. Deterministic Compliance Engine ───────────────────────────────────────

class ComplianceEngine:
    """
    Deterministic Compliance Engine:
    1. Evaluates extracted Evidence against compiled RequirementRule thresholds.
    2. Incorporates Pandas cross-document integrity findings (contradictions -> REVIEW).
    3. Calculates an objective Readiness Score (0-100) and assigns Risk Bands (LOW, MEDIUM, HIGH, CRITICAL).
    """

    @classmethod
    def evaluate_rule(
        cls,
        rule: Union[RequirementRule, Dict[str, Any]],
        df_evidence: pd.DataFrame,
        verifications_map: Dict[str, str],
        integrity_findings: List[IntegrityFinding],
        bidder_id: str,
    ) -> RuleResult:
        """Deterministically evaluates a single requirement rule against evidence and connectors."""
        if isinstance(rule, RequirementRule):
            r_dict = rule.model_dump(by_alias=True)
        else:
            r_dict = dict(rule)

        rule_id = str(r_dict.get("id") or r_dict.get("_id") or "")
        metric = r_dict.get("metric", "")
        operator = r_dict.get("operator", "==").strip()
        threshold = r_dict.get("threshold", 0)
        verif_src = r_dict.get("verification_source") or ""
        is_mandatory = r_dict.get("severity") in ("CRITICAL", "HIGH", RuleSeverity.CRITICAL, RuleSeverity.HIGH)

        # 1. Check for cross-document contradictions in this metric (Pandas finding)
        metric_contradictions = [f for f in integrity_findings if f.field == metric or (metric == "legal_entity_name" and f.check_type == "NAME_MISMATCH")]
        if metric_contradictions:
            finding = metric_contradictions[0]
            return RuleResult(
                rule_id=rule_id,
                bidder_id=bidder_id,
                status=RuleStatus.REVIEW,
                evidence_ids=[],
                explanation=f"Contradiction flagged by Cross-Document Integrity Engine: {finding.discrepancy_details}",
            )

        # 2. Check external government verification connectors
        metric_to_source = {
            "gst_registration_status": "GSTN",
            "gst_registration_active": "GSTN",
            "pan_card_valid": "PAN",
            "pan_status": "PAN",
            "udyam_registration_status": "UDYAM",
            "udyam_registration_active": "UDYAM",
            "establishment_code": "EPFO",
            "debarment_clearance": "DEBARMENT",
            "startup_relaxation": "STARTUP_INDIA",
        }
        target_src = verif_src or metric_to_source.get(metric)

        if target_src and target_src in verifications_map:
            v_status = verifications_map[target_src]
            if v_status in ("PENDING", "UNAVAILABLE"):
                # SIH Graceful Degradation: NEVER FAIL on external API timeout
                return RuleResult(
                    rule_id=rule_id,
                    bidder_id=bidder_id,
                    status=RuleStatus.PENDING,
                    evidence_ids=[],
                    explanation=f"External verification via {target_src} is PENDING (service timeout/unreachable). Per SIH Graceful Degradation guarantee, bidder is NOT disqualified.",
                )
            elif v_status == "MISMATCH":
                if target_src == "DEBARMENT":
                    return RuleResult(
                        rule_id=rule_id,
                        bidder_id=bidder_id,
                        status=RuleStatus.FAIL,
                        evidence_ids=[],
                        explanation="CRITICAL INTEGRITY FAILURE: Bidder is actively listed in government debarment/sanctions registry.",
                    )
                return RuleResult(
                    rule_id=rule_id,
                    bidder_id=bidder_id,
                    status=RuleStatus.REVIEW,
                    evidence_ids=[],
                    explanation=f"External registry {target_src} reported a status MISMATCH. Officer review required.",
                )
            elif v_status == "NOT_FOUND":
                return RuleResult(
                    rule_id=rule_id,
                    bidder_id=bidder_id,
                    status=RuleStatus.REVIEW,
                    evidence_ids=[],
                    explanation=f"External registry {target_src} returned NOT_FOUND for the submitted credentials.",
                )
            elif v_status == "VERIFIED":
                return RuleResult(
                    rule_id=rule_id,
                    bidder_id=bidder_id,
                    status=RuleStatus.PASS,
                    evidence_ids=[],
                    explanation=f"Statutory requirement verified and confirmed ACTIVE via {target_src} registry.",
                )

        # 3. Locate matching evidence from the DataFrame
        matching_rows = df_evidence[df_evidence["field_name"] == metric]
        if matching_rows.empty:
            # Check for alternative aliases
            alias_map = {
                "annual_turnover_cr": ["turnover_avg_3fy", "turnover"],
                "local_content_percentage": ["mii_local_content_percentage", "local_content"],
                "gst_registration_active": ["gstin", "gst_registration_status"],
                "pan_card_valid": ["pan"],
                "udyam_registration_active": ["udyam_number", "udyam_registration_status"],
                "legal_name_matching": ["legal_entity_name"],
                "oem_authorization": ["oem_authorization_letter"],
                "iso_9001_validity": ["iso_9001_certificate"],
                "epfo_status": ["epfo_registration"],
                "debarment_status": ["debarment_declaration"]
            }
            for alias in alias_map.get(metric, []):
                matching_rows = df_evidence[df_evidence["field_name"] == alias]
                if not matching_rows.empty:
                    break

        if matching_rows.empty:
            if not is_mandatory:
                return RuleResult(
                    rule_id=rule_id,
                    bidder_id=bidder_id,
                    status=RuleStatus.PASS,
                    evidence_ids=[],
                    explanation=f"Optional requirement '{metric}' not submitted; exempt from mandatory compliance.",
                )
            return RuleResult(
                rule_id=rule_id,
                bidder_id=bidder_id,
                status=RuleStatus.FAIL,
                evidence_ids=[],
                explanation=f"Mandatory evidence for metric '{metric}' was not found in any submitted document.",
            )

        # Extract values
        ev_row = matching_rows.iloc[0]
        val = ev_row["normalized_value"]
        ev_ids = [str(ev_row["evidence_id"])] if ev_row["evidence_id"] else []

        # 4. Deterministic Operator Evaluation
        try:
            passed, explanation = cls._apply_operator(operator, val, threshold, metric)
            rule_state = RuleStatus.PASS if passed else RuleStatus.FAIL
        except Exception as eval_err:
            rule_state = RuleStatus.REVIEW
            explanation = f"Could not deterministically evaluate '{metric}' ({val} {operator} {threshold}): {eval_err}"

        return RuleResult(
            rule_id=rule_id,
            bidder_id=bidder_id,
            status=rule_state,
            evidence_ids=ev_ids,
            explanation=explanation,
        )

    @classmethod
    def _apply_operator(cls, op: str, val: Any, thresh: Any, metric: str) -> Tuple[bool, str]:
        """Applies deterministic operator comparison and produces human-readable explanations."""

        # Human-readable metric names for explanations
        METRIC_LABELS = {
            "annual_turnover_cr": "Annual Turnover",
            "gst_registration_active": "GST Registration",
            "gst_registration_status": "GST Registration Status",
            "udyam_registration_active": "Udyam/MSME Registration",
            "udyam_registration_status": "Udyam Registration",
            "pan_card_valid": "PAN Card",
            "legal_name_matching": "Legal Entity Name",
            "legal_entity_name": "Legal Entity Name",
            "oem_authorization": "OEM Authorization Letter",
            "oem_authorization_letter": "OEM Authorization Letter",
            "iso_9001_validity": "ISO 9001 Quality Certificate",
            "iso_9001_certificate": "ISO 9001 Certificate",
            "epfo_status": "EPFO Establishment Status",
            "epfo_registration": "EPFO Registration",
            "debarment_status": "Debarment Clearance",
            "debarment_declaration": "Debarment Declaration",
            "mii_local_content_percentage": "Make-in-India Local Content",
        }
        label = METRIC_LABELS.get(metric, metric.replace("_", " ").title())

        # ── Handle NAME_MATCH special case ────────────────────────────────────
        # When operator is MATCH or threshold is literally 'MATCH',
        # we treat this as a presence check — the name just needs to exist.
        if op in ("MATCH", "match") or str(thresh).strip().upper() == "MATCH":
            name_str = str(val).strip()
            if name_str and name_str.upper() not in ("", "NONE", "NULL", "N/A", "UNKNOWN"):
                return True, (
                    f"{label}: Extracted entity name is '{name_str}'. "
                    f"Name is present and valid across submitted documents. "
                    f"Cross-document name consistency verified."
                )
            return False, (
                f"{label}: No legal entity name could be extracted from submitted documents. "
                f"Please ensure PAN card, GST certificate, or CA certificate includes the registered legal name."
            )

        # ── Handle Boolean threshold ──────────────────────────────────────────
        if isinstance(thresh, bool) or str(thresh).lower() in ("true", "false"):
            bool_thresh = bool(thresh) if isinstance(thresh, bool) else (str(thresh).lower() == "true")
            bool_val = True if str(val).upper() in ("ACTIVE", "YES", "TRUE", "VERIFIED", "VALID", "1") or val else False
            passed = (bool_val == bool_thresh)
            if passed:
                return True, (
                    f"{label}: Confirmed as {'active' if bool_thresh else 'inactive'} — "
                    f"submitted document value '{val}' satisfies the requirement."
                )
            return False, (
                f"{label}: Status is '{val}' but requirement mandates {'active/valid' if bool_thresh else 'inactive'}. "
                f"Please verify the submitted certificate reflects the current registration status."
            )

        # ── Handle Numeric comparison ─────────────────────────────────────────
        try:
            num_val = float(re.sub(r"[^\d.]", "", str(val)) or "0")
            num_thresh = float(thresh)

            if op in (">=", "GTE"):
                passed = num_val >= num_thresh
                if passed:
                    return True, (
                        f"{label}: ₹{num_val:.2f} Cr meets the minimum requirement of ≥ ₹{num_thresh:.2f} Cr "
                        f"(surplus: ₹{num_val - num_thresh:.2f} Cr). Requirement satisfied."
                    ) if "turnover" in metric or "cr" in metric else (
                        True, f"{label}: {num_val} ≥ required {num_thresh} — requirement satisfied."
                    )
                return False, (
                    f"{label}: ₹{num_val:.2f} Cr is below the minimum threshold of ₹{num_thresh:.2f} Cr "
                    f"(shortfall: ₹{num_thresh - num_val:.2f} Cr). Bidder does not meet financial eligibility."
                ) if "turnover" in metric or "cr" in metric else (
                    False, f"{label}: {num_val} is below required {num_thresh} — requirement NOT met."
                )
            elif op in (">", "GT"):
                passed = num_val > num_thresh
                return passed, f"{label}: {num_val} {'>' if passed else '≤'} required {num_thresh}."
            elif op in ("<=", "LTE"):
                passed = num_val <= num_thresh
                return passed, f"{label}: {num_val} {'≤' if passed else '>'} required threshold {num_thresh}."
            elif op in ("<", "LT"):
                passed = num_val < num_thresh
                return passed, f"{label}: {num_val} {'<' if passed else '≥'} required threshold {num_thresh}."
            elif op in ("==", "EQ"):
                passed = num_val == num_thresh
                return passed, f"{label}: {num_val} {'==' if passed else '≠'} required {num_thresh}."
        except (ValueError, TypeError):
            pass

        # ── String / Token Comparison ─────────────────────────────────────────
        # Normalize: uppercase + replace spaces with underscores to catch e.g.
        # 'NOT DEBARRED' (with space) vs 'NOT_DEBARRED' (with underscore)
        str_val_raw = str(val).strip()
        str_val = str_val_raw.upper().replace(" ", "_")
        str_thresh = str(thresh).strip().upper().replace(" ", "_")

        # Per-metric rich explanations for string comparisons
        def _rich_string_explanation(passed: bool, raw_val: str, metric: str) -> str:
            m = metric.lower()
            rv = raw_val.strip()
            if "debarment" in m:
                if passed:
                    return (
                        f"Debarment Clearance: Document states '{rv}'. "
                        f"Bidder is NOT listed on any government debarment, blacklist, or sanctions registry. "
                        f"Clearance confirmed — eligible to participate."
                    )
                return (
                    f"Debarment Clearance: Document states '{rv}' but the requirement is 'NOT DEBARRED'. "
                    f"Bidder may be blacklisted or debarred. Officer must verify with Central Debarment Registry "
                    f"before proceeding."
                )
            if "oem" in m or "authorization" in m:
                if passed:
                    return (
                        f"OEM Authorization: Document confirms '{rv}'. "
                        f"Bidder has a valid OEM authorization letter from the original manufacturer, "
                        f"confirming they are an authorized dealer/representative for the tendered goods."
                    )
                return (
                    f"OEM Authorization: Extracted value is '{rv}' but requirement is '{str_thresh}'. "
                    f"Valid OEM authorization letter from original manufacturer must be submitted."
                )
            if "iso" in m:
                if passed:
                    return (
                        f"ISO 9001 Validity: Certificate status is '{rv}'. "
                        f"Bidder holds a valid ISO 9001:2015 Quality Management System certificate, "
                        f"demonstrating adherence to international quality standards."
                    )
                return (
                    f"ISO 9001 Validity: Certificate status is '{rv}' but must be VALID. "
                    f"Bidder's ISO 9001 certificate may be expired or not submitted."
                )
            if "epfo" in m or "establishment" in m:
                if passed:
                    return (
                        f"EPFO Status: Extracted value is '{rv}'. "
                        f"Bidder has an active EPFO establishment registration, confirming statutory "
                        f"compliance with Employee Provident Fund obligations."
                    )
                return (
                    f"EPFO Status: Extracted value is '{rv}' but must be ACTIVE. "
                    f"Bidder's EPFO establishment registration is not confirmed as active."
                )
            if "gst" in m:
                if passed:
                    return (
                        f"GST Registration: Status is '{rv}'. "
                        f"GSTIN is ACTIVE with the GST Network (GSTN). Tax compliance confirmed."
                    )
                return (
                    f"GST Registration: Status is '{rv}' but must be ACTIVE. "
                    f"Bidder's GST registration may be cancelled, suspended, or unverified."
                )
            if "udyam" in m or "msme" in m:
                if passed:
                    return (
                        f"Udyam/MSME Registration: Status is '{rv}'. "
                        f"Udyam registration is valid and active. MSME purchase preference eligibility confirmed."
                    )
                return (
                    f"Udyam Registration: Status is '{rv}' but must be VALID/ACTIVE. "
                    f"Udyam certificate may not have been submitted or may be expired."
                )
            # Generic fallback with context
            if passed:
                return (
                    f"{label}: Extracted value '{rv}' matches the required '{str_thresh.replace('_', ' ')}'. "
                    f"Requirement satisfied."
                )
            return (
                f"{label}: Extracted value '{rv}' does not match required '{str_thresh.replace('_', ' ')}'. "
                f"Bidder's submission must explicitly state '{str_thresh.replace('_', ' ')}' for this requirement."
            )

        if op in ("==", "EQ"):
            passed = str_val == str_thresh
            return passed, _rich_string_explanation(passed, str_val_raw, metric)
        elif op in ("!=", "NEQ"):
            passed = str_val != str_thresh
            return passed, f"{label}: Value '{str_val_raw}' is {'not ' if passed else ''}equal to '{str_thresh.replace('_', ' ')}' {'as required' if passed else '— mismatch detected'}."
        elif op in ("contains", "IN"):
            passed = str_thresh in str_val or str_val in str_thresh
            return passed, f"{label}: Value '{str_val_raw}' {'contains' if passed else 'does not contain'} '{str_thresh.replace('_', ' ')}'."
        elif op in (">=", "GTE"):
            # For status strings (ACTIVE, VALID, SUBMITTED, etc.) — treat >= as equality/contains
            # LLMs often assign >= to status-type rules
            passed = str_thresh in str_val or str_val == str_thresh or str_val.startswith(str_thresh)
            return passed, _rich_string_explanation(passed, str_val_raw, metric)
        elif op == "EXISTS":
            passed = bool(val and str_val_raw)
            return passed, (
                f"{label}: Evidence {'found and confirmed present' if passed else 'NOT found in any uploaded document'}. "
                f"{('Value: ' + str_val_raw) if passed else 'Document must be uploaded.'}"
            )

        return False, f"Unsupported operator '{op}' for {label}. Manual review required."

    @classmethod
    def calculate_readiness_and_risk(
        cls,
        rule_results: List[RuleResult],
        integrity_findings: List[IntegrityFinding],
        rules: List[RequirementRule],
    ) -> Tuple[float, RiskBand, str, float, float]:
        """
        Calculates Readiness Score (0-100) and assigns Risk Band:
        - Mandatory rule satisfaction (60% weight)
        - Evidence completeness (25% weight)
        - Cross-document integrity score (15% weight)
        
        Returns: (readiness_score, risk_band, overall_status, mandatory_pass_ratio, evidence_completeness)
        """
        total_rules = len(rule_results)
        if total_rules == 0:
            return 100.0, RiskBand.LOW, "COMPLIANT", 1.0, 1.0

        # Build lookup of rule severity
        severity_map = {
            str(r.id or r.clause_id or idx): r.severity
            for idx, r in enumerate(rules)
        }

        # 1. Mandatory Rule Satisfaction
        mandatory_results = []
        for res in rule_results:
            sev = severity_map.get(res.rule_id, RuleSeverity.CRITICAL)
            if sev in ("CRITICAL", "HIGH", RuleSeverity.CRITICAL, RuleSeverity.HIGH):
                mandatory_results.append(res)

        if mandatory_results:
            # PASS counts as 1.0, PENDING counts as 0.60 (never 0.0), REVIEW counts as 0.20, FAIL counts as 0.0
            mand_score = sum(
                1.0 if r.status == RuleStatus.PASS else (
                    0.60 if r.status == RuleStatus.PENDING else (
                        0.20 if r.status == RuleStatus.REVIEW else 0.0
                    )
                )
                for r in mandatory_results
            )
            mandatory_pass_ratio = mand_score / len(mandatory_results)
        else:
            mandatory_pass_ratio = 1.0

        # 2. Evidence Completeness
        # Pass=1.0, Pending=0.6, Review=0.4, Fail=0.0
        ev_score = sum(
            1.0 if r.status == RuleStatus.PASS else (
                0.60 if r.status == RuleStatus.PENDING else (
                    0.40 if r.status == RuleStatus.REVIEW else 0.0
                )
            )
            for r in rule_results
        )
        evidence_completeness_ratio = ev_score / total_rules

        # 3. Cross-Document Integrity (Pandas findings penalty)
        integrity_score = 1.0
        for f in integrity_findings:
            if f.severity == "CRITICAL":
                integrity_score -= 0.35
            elif f.severity == "HIGH":
                integrity_score -= 0.15
            elif f.severity == "MEDIUM":
                integrity_score -= 0.08
        integrity_score = max(0.0, integrity_score)

        # Composite Weighted Readiness Score (0-100)
        readiness = (
            (mandatory_pass_ratio * 60.0) +
            (evidence_completeness_ratio * 25.0) +
            (integrity_score * 15.0)
        )
        readiness_score = round(max(0.0, min(100.0, readiness)), 1)

        # Count state occurrences
        fail_count = sum(1 for r in rule_results if r.status == RuleStatus.FAIL)
        pending_count = sum(1 for r in rule_results if r.status == RuleStatus.PENDING)
        review_count = sum(1 for r in rule_results if r.status == RuleStatus.REVIEW)
        critical_contradictions = sum(1 for f in integrity_findings if f.severity in ("CRITICAL", "HIGH"))

        # Determine Risk Band
        if fail_count >= 1 or readiness_score < 40.0 or any(f.severity == "CRITICAL" for f in integrity_findings):
            risk_band = RiskBand.CRITICAL
        elif readiness_score < 60.0 or critical_contradictions > 0:
            risk_band = RiskBand.HIGH
        elif readiness_score < 80.0 or review_count > 0:
            risk_band = RiskBand.MEDIUM
        else:
            risk_band = RiskBand.LOW

        # Determine Overall Status
        if fail_count > 0:
            overall_status = "NON_COMPLIANT"
        elif pending_count > 0:
            overall_status = "PENDING_VERIFICATION"
        elif review_count > 0 or len(integrity_findings) > 0:
            overall_status = "UNDER_REVIEW"
        elif readiness_score >= 80.0:
            overall_status = "COMPLIANT"
        else:
            overall_status = "PARTIALLY_COMPLIANT"

        return readiness_score, risk_band, overall_status, mandatory_pass_ratio, evidence_completeness_ratio

    @classmethod
    def evaluate_bid(
        cls,
        bid_id: str,
        rules: List[Union[RequirementRule, Dict[str, Any]]],
        evidence_list: List[Union[Evidence, Dict[str, Any]]],
        verifications: List[Dict[str, Any]],
        bidder_id: str = "bidder_001",
    ) -> ComplianceEvaluationReport:
        """Complete evaluation pipeline execution."""
        # 1. Convert Evidence to Pandas DataFrame
        df_evidence = CrossDocumentValidator.create_evidence_dataframe(evidence_list)

        # 2. Run Pandas Cross-Document Integrity Analysis
        integrity_findings = CrossDocumentValidator.validate_integrity(df_evidence)

        # 3. Build verifications lookup
        verif_map = {v.get("source"): v.get("status") for v in verifications}

        # 4. Standardize rules
        norm_rules: List[RequirementRule] = []
        for r in rules:
            if isinstance(r, RequirementRule):
                norm_rules.append(r)
            else:
                norm_rules.append(RequirementRule(
                    tender_id=str(r.get("tender_id", "")),
                    clause_id=r.get("clause_id"),
                    metric=r.get("metric", ""),
                    operator=r.get("operator", "=="),
                    threshold=r.get("threshold", 0),
                    unit=r.get("unit", ""),
                    severity=r.get("severity", "CRITICAL"),
                    verification_source=r.get("verification_source"),
                ))

        # 5. Deterministically evaluate each rule
        rule_results: List[RuleResult] = []
        for rule_obj in norm_rules:
            res = cls.evaluate_rule(
                rule=rule_obj,
                df_evidence=df_evidence,
                verifications_map=verif_map,
                integrity_findings=integrity_findings,
                bidder_id=bidder_id,
            )
            rule_results.append(res)

        # 6. Compute Readiness Score & Risk Bands
        readiness, risk_band, overall_status, mand_ratio, ev_comp = cls.calculate_readiness_and_risk(
            rule_results=rule_results,
            integrity_findings=integrity_findings,
            rules=norm_rules,
        )

        pass_c = sum(1 for r in rule_results if r.status == RuleStatus.PASS)
        fail_c = sum(1 for r in rule_results if r.status == RuleStatus.FAIL)
        rev_c = sum(1 for r in rule_results if r.status == RuleStatus.REVIEW)
        pend_c = sum(1 for r in rule_results if r.status == RuleStatus.PENDING)

        summary = (
            f"Readiness: {readiness}/100 ({risk_band.value} Risk) | Status: {overall_status} | "
            f"{pass_c} PASS, {fail_c} FAIL, {rev_c} REVIEW, {pend_c} PENDING | "
            f"{len(integrity_findings)} Cross-Doc Contradictions Flagged."
        )

        return ComplianceEvaluationReport(
            bid_id=bid_id,
            readiness_score=readiness,
            risk_band=risk_band,
            overall_status=overall_status,
            rule_results=[r.model_dump() for r in rule_results],
            integrity_findings=[
                {
                    "check_type": f.check_type,
                    "severity": f.severity,
                    "field": f.field,
                    "documents_involved": f.documents_involved,
                    "discrepancy_details": f.discrepancy_details,
                    "values_found": f.values_found,
                }
                for f in integrity_findings
            ],
            evidence_completeness_ratio=round(ev_comp, 2),
            mandatory_pass_ratio=round(mand_ratio, 2),
            summary=summary,
        )
