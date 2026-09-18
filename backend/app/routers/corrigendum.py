"""
GeM-Guard — Corrigendum Impact Analyzer Router
Strict Specifications:
1. Accepts mid-process tender rule amendments (corrigenda).
2. Discovers all submitted bids for the tender.
3. Re-evaluates strictly the changed rule against existing extracted evidence.
4. Produces an impact diff summary detailing flipped compliance statuses and score deltas.
5. Immutably logs corrigendum and impact analysis to the cryptographic SHA-256 audit chain.
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.database import doc_to_dict, get_db, to_oid, utcnow_str
from app.engine.audit import AuditEngine
from app.engine.compliance import ComplianceEngine, CrossDocumentValidator
from app.schemas.domain import RequirementRule, RuleResult, RuleStatus

logger = logging.getLogger("gemguard.routers.corrigendum")

router = APIRouter(tags=["corrigendum"])


class CorrigendumRequest(BaseModel):
    metric: str = Field(..., description="The metric being amended (e.g. annual_turnover_cr, local_content_percentage)")
    new_threshold: Any = Field(..., description="The new threshold value (e.g. 10.0 Cr, 40%)")
    operator: Optional[str] = Field(default=">=", description="Comparison operator (>=, >, <=, <, ==)")
    clause_id: Optional[str] = Field(default=None, description="Tender clause reference (e.g. 3.1)")
    corrigendum_number: Optional[str] = Field(default="CORR-01", description="Official Corrigendum identifier")
    reason: str = Field(..., description="Justification / Pre-bid meeting query reference")
    actor: Optional[str] = Field(default="officer@gem.gov.in", description="Issuing Procurement Officer")
    apply_changes: Optional[bool] = Field(default=True, description="Commit changes to rules and bids in database")


@router.post("/api/v1/tenders/{tender_id}/corrigendum")
@router.post("/api/tenders/{tender_id}/corrigendum")
@router.post("/tenders/{tender_id}/corrigendum")
async def issue_corrigendum_and_analyze_impact(
    tender_id: str,
    body: CorrigendumRequest,
    db=Depends(get_db),
):
    """
    Issue a mid-process corrigendum amendment to a tender rule.
    Identifies all submitted bids for the tender, re-evaluates strictly the changed rule
    against existing extracted evidence, and produces an impact diff summary.
    """
    toid = to_oid(tender_id)
    tender = await db["tenders"].find_one({"_id": toid})
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    # 1. Locate existing rule for this metric
    rule_query = {"tender_id": tender_id, "metric": body.metric}
    existing_rule = await db["rules"].find_one(rule_query)
    if not existing_rule:
        # Fallback to clause_id or any rule for metric
        existing_rule = await db["rules"].find_one({"tender_id": tender_id})
        if not existing_rule:
            raise HTTPException(
                status_code=404,
                detail=f"No compiled compliance rules found for tender {tender_id} to amend.",
            )

    old_threshold = existing_rule.get("threshold", 0)
    old_operator = existing_rule.get("operator", ">=")
    rule_id_str = str(existing_rule["_id"])

    # Build updated RequirementRule model
    amended_rule = RequirementRule(
        tender_id=tender_id,
        clause_id=body.clause_id or existing_rule.get("clause_id", "3.1"),
        metric=body.metric,
        operator=body.operator or old_operator,
        threshold=body.new_threshold,
        unit=existing_rule.get("unit", ""),
        severity=existing_rule.get("severity", "CRITICAL"),
        verification_source=existing_rule.get("verification_source"),
    )

    # 2. Fetch all bids submitted for this tender
    bids_cursor = db["bids"].find({"tender_id": tender_id})
    bids = await bids_cursor.to_list(200)

    bids_evaluated_count = len(bids)
    impacted_bids_count = 0
    flips_to_pass = 0
    flips_to_fail = 0
    status_flips: List[Dict[str, Any]] = []

    for bid in bids:
        bid_id_str = str(bid["_id"])
        bidder_id = bid.get("bidder_id", "bidder")

        # Fetch extracted evidence for this bid
        ev_cursor = db["evidence"].find({"$or": [{"bid_id": bid_id_str}, {"package_id": bid_id_str}]})
        ev_list = await ev_cursor.to_list(100)
        df_evidence = CrossDocumentValidator.create_evidence_dataframe(ev_list)

        # Existing rule result for this metric
        prev_results = bid.get("evaluation_results", [])
        prior_rule_res = next(
            (r for r in prev_results if r.get("metric") == body.metric or r.get("rule_id") == rule_id_str),
            None,
        )
        prior_status = prior_rule_res.get("status", "FAIL") if prior_rule_res else "FAIL"

        # 3. Strictly re-evaluate the changed rule
        new_rule_res = ComplianceEngine.evaluate_rule(
            rule=amended_rule,
            df_evidence=df_evidence,
            verifications_map={},
            integrity_findings=[],
            bidder_id=bidder_id,
        )
        new_status = new_rule_res.status.value

        is_flipped = (prior_status != new_status)
        if is_flipped:
            impacted_bids_count += 1
            if prior_status in ("FAIL", "REVIEW") and new_status == "PASS":
                flips_to_pass += 1
                delta_impact = "ELIGIBILITY_GAINED (PASS)"
            elif prior_status == "PASS" and new_status in ("FAIL", "REVIEW"):
                flips_to_fail += 1
                delta_impact = "DISQUALIFIED (FAIL)"
            else:
                delta_impact = f"STATUS_CHANGED ({prior_status} -> {new_status})"

            status_flips.append({
                "bid_id": bid_id_str,
                "bidder_id": bidder_id,
                "bidder_name": bid.get("bidder_name", "Enterprise"),
                "previous_status": prior_status,
                "new_status": new_status,
                "delta_impact": delta_impact,
                "explanation": new_rule_res.explanation,
            })

            # 4. Commit changes to bid if apply_changes=True
            if body.apply_changes:
                # Update evaluation results in bid
                updated_results = []
                found = False
                for r in prev_results:
                    if r.get("metric") == body.metric or r.get("rule_id") == rule_id_str:
                        r["status"] = new_status
                        r["explanation"] = f"[CORRIGENDUM {body.corrigendum_number}]: {new_rule_res.explanation}"
                        r["corrigendum_applied"] = body.corrigendum_number
                        found = True
                    updated_results.append(r)
                if not found:
                    updated_results.append(new_rule_res.model_dump())

                # Recompute overall status
                has_fail = any(r.get("status") == "FAIL" for r in updated_results)
                has_pending = any(r.get("status") == "PENDING" for r in updated_results)
                has_rev = any(r.get("status") == "REVIEW" for r in updated_results)

                if has_fail:
                    updated_overall = "NON_COMPLIANT"
                    updated_risk = 85.0
                elif has_pending:
                    updated_overall = "PENDING_VERIFICATION"
                    updated_risk = 25.0
                elif has_rev:
                    updated_overall = "UNDER_REVIEW"
                    updated_risk = 35.0
                else:
                    updated_overall = "COMPLIANT"
                    updated_risk = 15.0

                await db["bids"].update_one(
                    {"_id": bid["_id"]},
                    {"$set": {
                        "evaluation_results": updated_results,
                        "compliance_status": updated_overall,
                        "risk_score": updated_risk,
                        "last_corrigendum_applied": body.corrigendum_number,
                        "corrigendum_updated_at": utcnow_str(),
                    }},
                )

    # 5. Commit rule update to rules collection if apply_changes=True
    if body.apply_changes:
        await db["rules"].update_one(
            {"_id": existing_rule["_id"]},
            {"$set": {
                "threshold": body.new_threshold,
                "operator": body.operator or old_operator,
                "last_corrigendum": body.corrigendum_number,
                "updated_at": utcnow_str(),
            }},
        )

        # Store Corrigendum Record
        corrigendum_doc = {
            "tender_id": tender_id,
            "corrigendum_number": body.corrigendum_number,
            "metric": body.metric,
            "old_threshold": old_threshold,
            "new_threshold": body.new_threshold,
            "operator": body.operator or old_operator,
            "reason": body.reason,
            "actor": body.actor,
            "bids_evaluated_count": bids_evaluated_count,
            "impacted_bids_count": impacted_bids_count,
            "flips_to_pass": flips_to_pass,
            "flips_to_fail": flips_to_fail,
            "issued_at": utcnow_str(),
        }
        await db["corrigenda"].insert_one(corrigendum_doc)

    # 6. Log to Cryptographic Audit Chain
    audit_record = await AuditEngine.log_corrigendum(
        db=db,
        tender_id=tender_id,
        actor=body.actor or "officer@gem.gov.in",
        details={
            "corrigendum_number": body.corrigendum_number,
            "metric": body.metric,
            "old_threshold": old_threshold,
            "new_threshold": body.new_threshold,
            "reason": body.reason,
            "bids_evaluated_count": bids_evaluated_count,
            "impacted_bids_count": impacted_bids_count,
            "flips_to_pass": flips_to_pass,
            "flips_to_fail": flips_to_fail,
        },
    )

    summary_text = (
        f"Corrigendum {body.corrigendum_number} amended '{body.metric}' from {old_threshold} to {body.new_threshold}. "
        f"Evaluated {bids_evaluated_count} bids: {impacted_bids_count} impacted ({flips_to_pass} gained compliance, {flips_to_fail} disqualified)."
    )

    return {
        "status": "success",
        "tender_id": tender_id,
        "corrigendum_number": body.corrigendum_number,
        "metric": body.metric,
        "old_threshold": old_threshold,
        "new_threshold": body.new_threshold,
        "operator": body.operator or old_operator,
        "bids_evaluated_count": bids_evaluated_count,
        "impacted_bids_count": impacted_bids_count,
        "flips_to_pass_count": flips_to_pass,
        "flips_to_fail_count": flips_to_fail,
        "status_flips": status_flips,
        "applied": body.apply_changes,
        "summary": summary_text,
        "event_hash": audit_record.get("event_hash"),
        "prev_hash": audit_record.get("prev_hash"),
    }


@router.get("/api/v1/tenders/{tender_id}/corrigenda")
@router.get("/api/tenders/{tender_id}/corrigenda")
@router.get("/tenders/{tender_id}/corrigenda")
async def list_tender_corrigenda(tender_id: str, db=Depends(get_db)):
    """List all historical corrigenda issued for a tender."""
    cursor = db["corrigenda"].find({"tender_id": tender_id}).sort("issued_at", -1)
    items = await cursor.to_list(100)
    return [doc_to_dict(c) for c in items]
