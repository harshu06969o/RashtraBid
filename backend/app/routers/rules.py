"""
GeM-Guard — Rules Router
Modular routing for Requirement Rules extraction, CRUD, and deterministic verification.
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.database import doc_to_dict, get_db, to_oid, utcnow_str
from app.schemas.domain import RequirementRule, RuleSeverity

logger = logging.getLogger("gemguard.routers.rules")

router = APIRouter(tags=["rules"])


class CreateRuleRequest(BaseModel):
    tender_id: str
    clause_id: Optional[str] = None
    metric: str
    operator: str
    threshold: Any
    unit: Optional[str] = ""
    severity: Optional[str] = "CRITICAL"
    conditions: Optional[Dict[str, Any]] = None
    evidence_type: Optional[str] = None
    verification_source: Optional[str] = None


class TestRuleRequest(BaseModel):
    metric: str
    operator: str
    threshold: Any
    test_value: Any


@router.get("/api/rules")
@router.get("/rules")
async def list_rules(
    tender_id: Optional[str] = Query(None, description="Filter rules by Tender ID"),
    db=Depends(get_db),
):
    """List requirement rules, optionally filtered by tender_id."""
    query = {"tender_id": tender_id} if tender_id else {}
    cursor = db["rules"].find(query)
    rules = await cursor.to_list(200)
    return [doc_to_dict(r) for r in rules]


@router.get("/api/rules/{rule_id}")
@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str, db=Depends(get_db)):
    """Get requirement rule by ID."""
    rule = await db["rules"].find_one({"_id": to_oid(rule_id)})
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return doc_to_dict(rule)


@router.post("/api/rules", status_code=status.HTTP_201_CREATED)
@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(body: CreateRuleRequest, db=Depends(get_db)):
    """Create a new requirement rule validating with RequirementRule domain model."""
    # Domain model validation
    domain_rule = RequirementRule(
        tender_id=body.tender_id,
        clause_id=body.clause_id,
        metric=body.metric,
        operator=body.operator,
        threshold=body.threshold,
        unit=body.unit or "",
        severity=body.severity or "CRITICAL",
        conditions=body.conditions,
        evidence_type=body.evidence_type,
        verification_source=body.verification_source,
    )
    doc_data = domain_rule.model_dump(by_alias=True, exclude_none=True)
    doc_data.pop("id", None)
    doc_data.pop("_id", None)
    doc_data["created_at"] = utcnow_str()

    res = await db["rules"].insert_one(doc_data)
    created = await db["rules"].find_one({"_id": res.inserted_id})
    return doc_to_dict(created)


@router.put("/api/rules/{rule_id}")
@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, body: Dict[str, Any], db=Depends(get_db)):
    """Update requirement rule."""
    oid = to_oid(rule_id)
    body.pop("_id", None)
    body.pop("id", None)
    body["updated_at"] = utcnow_str()
    res = await db["rules"].update_one({"_id": oid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    updated = await db["rules"].find_one({"_id": oid})
    return doc_to_dict(updated)


@router.delete("/api/rules/{rule_id}")
@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, db=Depends(get_db)):
    """Delete requirement rule."""
    oid = to_oid(rule_id)
    res = await db["rules"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return {"status": "deleted", "rule_id": rule_id}


@router.post("/api/rules/test")
@router.post("/rules/test")
async def test_rule(body: TestRuleRequest):
    """
    Test evaluate an operator and threshold against a sample test value.
    Supports operators: >=, >, <=, <, ==, !=, contains.
    """
    op = body.operator.strip()
    thresh = body.threshold
    val = body.test_value

    passed = False
    try:
        if op == ">=":
            passed = float(val) >= float(thresh)
        elif op == ">":
            passed = float(val) > float(thresh)
        elif op == "<=":
            passed = float(val) <= float(thresh)
        elif op == "<":
            passed = float(val) < float(thresh)
        elif op == "==":
            passed = str(val).lower() == str(thresh).lower()
        elif op == "!=":
            passed = str(val).lower() != str(thresh).lower()
        elif op == "contains":
            passed = str(thresh).lower() in str(val).lower()
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported operator: {op}")
    except (ValueError, TypeError) as conv_err:
        return {
            "status": "ERROR",
            "passed": False,
            "explanation": f"Type conversion failed for values: {val} vs {thresh} ({conv_err})",
        }

    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "explanation": f"Checked '{val}' {op} '{thresh}' -> Result: {passed}",
    }
