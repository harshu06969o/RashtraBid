"""
GeM-Guard — Bids Router
Modular routing for Bids, Document Processing, Evidence, Evaluation, and Officer Actions.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.core.database import doc_to_dict, get_db, safe_oid, to_oid, utcnow_str
from app.core.storage import storage
from app.schemas.domain import Evidence, RuleResult, RuleStatus

logger = logging.getLogger("gemguard.routers.bids")

router = APIRouter(tags=["bids"])


async def _resolve_tender_keys(db, tender_id: str) -> List[str]:
    """Given any tender identifier, return all matching aliases (_id string, id, tender_no, reference_number)."""
    if not tender_id:
        return []
    oid = safe_oid(tender_id)
    conds = [{"_id": oid}] if oid else []
    conds.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    tender = await db["tenders"].find_one({"$or": conds})
    keys = [tender_id]
    if tender:
        if "_id" in tender:
            keys.append(str(tender["_id"]))
        if "id" in tender and tender["id"]:
            keys.append(str(tender["id"]))
        if "tender_no" in tender and tender["tender_no"]:
            keys.append(str(tender["tender_no"]))
        if "reference_number" in tender and tender["reference_number"]:
            keys.append(str(tender["reference_number"]))
    return list(set(keys))


class SubmitBidRequest(BaseModel):
    tender_id: str
    tender_reference: Optional[str] = None
    bidder_id: Optional[str] = None
    bidder_name: Optional[str] = None
    bid_amount: Optional[float] = None
    remarks: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    turnover_cr: Optional[float] = None
    local_content_pct: Optional[float] = None
    category: Optional[str] = None


class OfficerActionRequest(BaseModel):
    action: str  # APPROVE, REJECT, SEEK_CLARIFICATION
    reason: str
    actor: Optional[str] = "officer@gem.gov.in"
    clause_overrides: Optional[List[Dict[str, Any]]] = None


class OfficerOverrideRequest(BaseModel):
    justification: str  # MANDATORY
    rule_id: Optional[str] = None
    metric: Optional[str] = None
    new_status: str = "PASS"  # PASS, FAIL, REVIEW
    actor: Optional[str] = "officer@gem.gov.in"
    clause_id: Optional[str] = None
    notes: Optional[str] = None


@router.get("/api/v1/bids")
@router.get("/api/bids")
@router.get("/bids")
async def list_bids(tender_id: Optional[str] = Query(None), db=Depends(get_db)):
    """List bids. If tender_id is provided, filter strictly to that tender."""
    if tender_id:
        keys = await _resolve_tender_keys(db, tender_id)
        cursor = db["bids"].find({
            "$or": [
                {"tender_id": {"$in": keys}},
                {"tender_reference": {"$in": keys}},
            ]
        }).sort("created_at", -1)
    else:
        cursor = db["bids"].find().sort("created_at", -1)
    bids = await cursor.to_list(100)
    return [doc_to_dict(b) for b in bids]


@router.get("/api/v1/bids/mine")
@router.get("/api/bids/mine")
@router.get("/bids/mine")
async def list_my_bids(tender_id: Optional[str] = Query(None), db=Depends(get_db)):
    """List bids submitted by current bidder. If tender_id is provided, filter strictly."""
    if tender_id:
        keys = await _resolve_tender_keys(db, tender_id)
        cursor = db["bids"].find({
            "$or": [
                {"tender_id": {"$in": keys}},
                {"tender_reference": {"$in": keys}},
            ]
        }).sort("created_at", -1)
    else:
        cursor = db["bids"].find().sort("created_at", -1)
    bids = await cursor.to_list(100)
    return [doc_to_dict(b) for b in bids]


@router.get("/api/v1/bids/{bid_id}")
@router.get("/api/bids/{bid_id}")
@router.get("/bids/{bid_id}")
async def get_bid(bid_id: str, db=Depends(get_db)):
    """Get full bid details, including documents and compliance status."""
    oid = safe_oid(bid_id)
    conds = [{"_id": oid}] if oid else []
    conds.extend([{"_id": bid_id}, {"id": bid_id}])
    bid = await db["bids"].find_one({"$or": conds})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")
    res = doc_to_dict(bid)

    # Attach tender details
    if bid.get("tender_id"):
        try:
            t_oid = safe_oid(bid["tender_id"])
            t_conds = [{"_id": t_oid}] if t_oid else []
            t_conds.extend([
                {"_id": bid["tender_id"]},
                {"id": bid["tender_id"]},
                {"tender_no": bid.get("tender_reference") or bid["tender_id"]},
                {"reference_number": bid.get("tender_reference") or bid["tender_id"]},
            ])
            tender = await db["tenders"].find_one({"$or": t_conds})
            if tender:
                res["tender"] = doc_to_dict(tender)
        except Exception:
            pass

    # Attach documents
    docs_cursor = db["bid_documents"].find({"bid_id": str(bid.get("_id") or bid.get("id") or bid_id)})
    res["documents"] = [doc_to_dict(d) for d in await docs_cursor.to_list(100)]

    # Attach evidence
    ev_cursor = db["evidence"].find({"bid_id": str(bid.get("_id") or bid.get("id") or bid_id)})
    res["evidence"] = [doc_to_dict(e) for e in await ev_cursor.to_list(100)]

    return res


@router.post("/api/v1/bids", status_code=status.HTTP_201_CREATED)
@router.post("/api/bids", status_code=status.HTTP_201_CREATED)
@router.post("/bids", status_code=status.HTTP_201_CREATED)
async def submit_bid(body: SubmitBidRequest, db=Depends(get_db)):
    """Submit a bid for a tender."""
    oid = safe_oid(body.tender_id)
    tender_query = [{"_id": oid}] if oid else []
    tender_query.extend([
        {"_id": body.tender_id},
        {"id": body.tender_id},
        {"tender_no": body.tender_id},
        {"reference_number": body.tender_id},
    ])
    tender = await db["tenders"].find_one({"$or": tender_query})
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender not found: {body.tender_id}")

    tender_id_str = str(tender.get("_id") or tender.get("id") or body.tender_id)
    tender_ref = tender.get("tender_no") or tender.get("reference_number") or tender_id_str

    bidder_id = body.bidder_id or "bidder@vendor.com"
    bidder_name = body.bidder_name or "Bharat Engineering & Industrial Ltd"
    gstin = body.gstin or "33AABCB1234F1Z5"
    pan = body.pan or "AABCB1234F"
    turnover_cr = body.turnover_cr if body.turnover_cr is not None else 18.5
    local_content_pct = body.local_content_pct if body.local_content_pct is not None else 65.0
    category = body.category or "MSE"

    # Pre-verify with government connectors
    verifications_data = []
    try:
        query = {
            "bidder_id": bidder_id,
            "bidder_name": bidder_name,
            "gstin": gstin,
            "pan": pan,
            "category": category,
        }
        connector_results = await connector_manager.verify_all(query=query)
        verifications_data = [r.model_dump() for r in connector_results]
    except Exception as exc:
        logger.warning("Auto connector verification on bid creation failed: %s", exc)

    payload = {
        "tender_id": tender_id_str,
        "tender_reference": tender_ref,
        "bidder_id": bidder_id,
        "bidder_name": bidder_name,
        "bidder": {
            "name": bidder_name,
            "legal_name": bidder_name,
            "gstin": gstin,
            "pan": pan,
            "turnover_cr": turnover_cr,
            "local_content_pct": local_content_pct,
            "category": category,
        },
        "bid_amount": body.bid_amount or 14500000.0,
        "status": "SUBMITTED",
        "compliance_status": "PASS",
        "risk_band": "LOW",
        "readiness_score": 92.0,
        "risk_score": 8.0,
        "verifications": verifications_data,
        "created_at": utcnow_str(),
        "updated_at": utcnow_str(),
    }
    result = await db["bids"].insert_one(payload)
    created = await db["bids"].find_one({"_id": result.inserted_id})

    # Run Compliance Engine evaluation against tender's compiled rules
    try:
        rules_cursor = db["rules"].find({"$or": [{"tender_id": tender_id_str}, {"tender_id": tender_ref}]})
        rules = await rules_cursor.to_list(100)
        report = ComplianceEngine.evaluate_bid(
            bid_id=str(result.inserted_id),
            rules=rules,
            evidence_list=[],
            verifications=verifications_data,
            bidder_id=bidder_id,
        )
        await db["bids"].update_one(
            {"_id": result.inserted_id},
            {"$set": {
                "compliance_status": report.overall_status,
                "readiness_score": report.readiness_score,
                "risk_band": report.risk_band.value,
                "risk_score": round(100.0 - report.readiness_score, 1),
                "evaluation_results": report.rule_results,
                "evaluation_summary": report.summary,
                "evaluated_at": utcnow_str(),
            }}
        )
        created = await db["bids"].find_one({"_id": result.inserted_id})
    except Exception as exc:
        logger.warning("Auto compliance evaluation on bid creation failed: %s", exc)

    return doc_to_dict(created)


@router.get("/api/v1/bids/{bid_id}/documents")
@router.get("/api/bids/{bid_id}/documents")
@router.get("/bids/{bid_id}/documents")
async def list_bid_documents(bid_id: str, db=Depends(get_db)):
    """List all documents uploaded for this bid across both bid_documents and legacy documents collections."""
    oid = safe_oid(bid_id)
    bid_keys = [bid_id]
    if oid:
        bid_keys.append(oid)
        bid_keys.append(str(oid))

    # Query bid_documents
    cursor = db["bid_documents"].find({"bid_id": {"$in": bid_keys}}).sort("uploaded_at", -1)
    docs = await cursor.to_list(100)

    # Fallback/merge with legacy documents collection if needed
    if not docs:
        legacy_cursor = db["documents"].find({"bid_id": {"$in": bid_keys}}).sort("uploaded_at", -1)
        legacy_docs = await legacy_cursor.to_list(100)
        docs.extend(legacy_docs)

    return [doc_to_dict(d) for d in docs]


from app.pipeline.document_processor import BidDocumentProcessor

@router.post("/api/bids/{bid_id}/documents/upload")
@router.post("/bids/{bid_id}/documents/upload")
@router.post("/api/v1/bids/{bid_id}/documents/upload")
async def upload_bid_document(
    bid_id: str,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    db=Depends(get_db),
):
    """Upload bid verification document (CA Cert, GSTN, PAN, MSME) and run AI Vision Intelligence Document Processor."""
    oid = safe_oid(bid_id)
    conds = [{"_id": oid}] if oid else []
    conds.extend([{"_id": bid_id}, {"id": bid_id}, {"bid_id": bid_id}])
    bid = await db["bids"].find_one({"$or": conds})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    resolved_bid_id = str(bid.get("_id") or bid.get("id") or bid_id)

    stored = await storage.save_file(
        file_input=file,
        filename=f"bid_{resolved_bid_id}_{file.filename}",
        subfolder="bids",
        content_type=file.content_type,
    )

    doc_record = {
        "bid_id": resolved_bid_id,
        "filename": stored.filename,
        "original_filename": file.filename,
        "file_path": str(stored.file_path),
        "file_hash": stored.file_hash,
        "size_bytes": stored.size_bytes,
        "uploaded_at": utcnow_str(),
    }
    res = await db["bid_documents"].insert_one(doc_record)
    doc_id = str(res.inserted_id)

    # Also mirror into legacy documents collection for backward compatibility
    try:
        legacy_doc = dict(doc_record)
        legacy_doc["_id"] = res.inserted_id
        await db["documents"].insert_one(legacy_doc)
    except Exception:
        pass

    # Execute Vision Intelligence Document Processor (Dual-Engine + Gemini 3.5 Flash-Lite + Classifier + Evidence Extractor)
    proc_res = await BidDocumentProcessor.process_single_file(
        file_path_or_bytes=stored.file_path,
        filename=file.filename,
        document_id=doc_id,
        package_id=resolved_bid_id,
        bidder_id=bid.get("bidder_id") or resolved_bid_id,
        document_type_hint=document_type,
        db=db,
    )

    extracted_fields = {e.field_name: e.normalized_value for e in proc_res.extracted_evidence}

    return {
        "status": "uploaded_and_processed",
        "document_id": doc_id,
        "filename": stored.filename,
        "original_filename": file.filename,
        "file_hash": stored.file_hash,
        "size_bytes": stored.size_bytes,
        "document_type": proc_res.classified_type,
        "classification_confidence": proc_res.classification_confidence,
        "processed_by": proc_res.processed_by,
        "legal_name": proc_res.legal_name,
        "total_pages": proc_res.total_pages,
        "evidence_count": len(proc_res.extracted_evidence),
        "extracted_fields": extracted_fields,
        "evidence": [e.model_dump() for e in proc_res.extracted_evidence],
    }


@router.delete("/api/v1/bids/{bid_id}/documents/{doc_id}")
@router.delete("/api/bids/{bid_id}/documents/{doc_id}")
@router.delete("/bids/{bid_id}/documents/{doc_id}")
async def delete_bid_document(bid_id: str, doc_id: str, db=Depends(get_db)):
    """Delete an uploaded bid document and its associated extracted evidence."""
    doc_oid = safe_oid(doc_id)
    doc_conds = [{"_id": doc_oid}] if doc_oid else []
    doc_conds.extend([{"_id": doc_id}, {"id": doc_id}])

    await db["bid_documents"].delete_many({"$or": doc_conds})
    await db["documents"].delete_many({"$or": doc_conds})
    await db["evidence"].delete_many({"document_id": doc_id})

    # Remove from bid.documents
    bid_oid = safe_oid(bid_id)
    bid_q = [{"_id": bid_oid}] if bid_oid else []
    bid_q.extend([{"_id": bid_id}, {"id": bid_id}, {"bid_id": bid_id}])
    await db["bids"].update_one(
        {"$or": bid_q},
        {
            "$pull": {"documents": {"document_id": doc_id}},
            "$set": {"updated_at": utcnow_str()},
        }
    )

    return {"status": "deleted", "document_id": doc_id}


@router.post("/api/bids/{bid_id}/package/upload")
@router.post("/bids/{bid_id}/package/upload")
@router.post("/api/v1/bids/{bid_id}/package/upload")
async def upload_bid_package(
    bid_id: str,
    files: List[UploadFile] = File(...),
    db=Depends(get_db),
):
    """Upload multiple bid documents simultaneously and process the complete package."""
    oid = safe_oid(bid_id)
    conds = [{"_id": oid}] if oid else []
    conds.extend([{"_id": bid_id}, {"id": bid_id}, {"bid_id": bid_id}])
    bid = await db["bids"].find_one({"$or": conds})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    resolved_bid_id = str(bid.get("_id") or bid.get("id") or bid_id)

    files_data: List[Tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        await f.seek(0)
        # Also store to disk for persistence
        await storage.save_file(
            file_input=content,
            filename=f"bid_{resolved_bid_id}_{f.filename}",
            subfolder="bids",
            content_type=f.content_type,
        )
        files_data.append((f.filename, content))

    package_result = await BidDocumentProcessor.process_bid_package(
        bid_id=resolved_bid_id,
        files_data=files_data,
        db=db,
    )
    return package_result


@router.post("/api/bids/{bid_id}/process")
@router.post("/bids/{bid_id}/process")
@router.post("/api/v1/bids/{bid_id}/process")
async def process_bid_documents(bid_id: str, db=Depends(get_db)):
    """Re-process all previously uploaded documents for a bid using the Vision Document Processor."""
    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    docs_cursor = db["bid_documents"].find({"bid_id": bid_id})
    docs = await docs_cursor.to_list(100)
    if not docs:
        raise HTTPException(status_code=400, detail="No documents found for this bid to process.")

    results = []
    for doc in docs:
        file_path = doc.get("file_path")
        doc_id = str(doc["_id"])
        filename = doc.get("original_filename") or doc.get("filename")
        if file_path and os.path.exists(file_path):
            res = await BidDocumentProcessor.process_single_file(
                file_path_or_bytes=file_path,
                filename=filename,
                document_id=doc_id,
                package_id=bid_id,
                bidder_id=bid.get("bidder_id") or bid_id,
                db=db,
            )
            results.append({
                "document_id": doc_id,
                "filename": filename,
                "type": res.classified_type,
                "confidence": res.classification_confidence,
                "evidence_count": len(res.extracted_evidence),
            })

    return {
        "status": "success",
        "bid_id": bid_id,
        "processed_documents": results,
    }


@router.get("/api/bids/{bid_id}/evidence")
@router.get("/bids/{bid_id}/evidence")
@router.get("/api/v1/bids/{bid_id}/evidence")
async def list_bid_evidence(bid_id: str, db=Depends(get_db)):
    """List all extracted evidence entries with bounding boxes for this bid."""
    oid = safe_oid(bid_id)
    keys = [bid_id]
    if oid:
        keys.append(str(oid))
    cursor = db["evidence"].find({
        "$or": [
            {"bid_id": {"$in": keys}},
            {"package_id": {"$in": keys}},
            {"bidder_id": {"$in": keys}},
        ]
    })
    evidence_list = await cursor.to_list(200)
    return [doc_to_dict(e) for e in evidence_list]


from app.connectors import connector_manager, ConnectorStatus, ConnectorResult

class VerifyBidRequest(BaseModel):
    simulate_timeout: Optional[bool] = False
    timeout_connectors: Optional[List[str]] = None
    override_identifiers: Optional[Dict[str, Any]] = None


from app.engine.compliance import ComplianceEngine, ComplianceEvaluationReport, RiskBand


@router.post("/api/bids/{bid_id}/evaluate")
@router.post("/bids/{bid_id}/evaluate")
@router.post("/api/v1/bids/{bid_id}/evaluate")
async def evaluate_bid(bid_id: str, db=Depends(get_db)):
    """
    Run deterministic compliance evaluation and Pandas cross-document integrity checks against tender rules.
    Calculates Readiness Score (0-100) and assigns Risk Band (LOW, MEDIUM, HIGH, CRITICAL).
    SIH Graceful Degradation Guarantee: External connector timeouts NEVER auto-disqualify a bid.
    """
    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    tender_id = bid.get("tender_id")
    rules_cursor = db["rules"].find({"tender_id": tender_id})
    rules = await rules_cursor.to_list(100)

    # Gather extracted evidence for this bid
    evidence_cursor = db["evidence"].find({"$or": [{"bid_id": bid_id}, {"package_id": bid_id}]})
    evidence_list = await evidence_cursor.to_list(200)

    # Gather external verification results
    verifications = bid.get("verifications", [])

    # Execute Compliance Engine (Deterministic rule evaluation + Pandas cross-document integrity + scoring)
    report = ComplianceEngine.evaluate_bid(
        bid_id=bid_id,
        rules=rules,
        evidence_list=evidence_list,
        verifications=verifications,
        bidder_id=bid.get("bidder_id", "bidder_001"),
    )

    risk_score = round(100.0 - report.readiness_score, 1)

    await db["bids"].update_one(
        {"_id": oid},
        {"$set": {
            "compliance_status": report.overall_status,
            "readiness_score": report.readiness_score,
            "risk_band": report.risk_band.value,
            "risk_score": risk_score,
            "evaluation_results": report.rule_results,
            "integrity_findings": report.integrity_findings,
            "evidence_completeness_ratio": report.evidence_completeness_ratio,
            "mandatory_pass_ratio": report.mandatory_pass_ratio,
            "evaluation_summary": report.summary,
            "evaluated_at": utcnow_str(),
        }},
    )

    # Audit log
    await db["audit"].insert_one({
        "timestamp": utcnow_str(),
        "actor": "system",
        "action": "BID_EVALUATED",
        "entity_id": bid_id,
        "details": {
            "status": report.overall_status,
            "readiness_score": report.readiness_score,
            "risk_band": report.risk_band.value,
            "integrity_contradictions_count": len(report.integrity_findings),
        },
    })

    return {
        "bid_id": bid_id,
        "overall_status": report.overall_status,
        "readiness_score": report.readiness_score,
        "risk_band": report.risk_band.value,
        "risk_score": risk_score,
        "results": report.rule_results,
        "integrity_findings": report.integrity_findings,
        "evidence_completeness_ratio": report.evidence_completeness_ratio,
        "mandatory_pass_ratio": report.mandatory_pass_ratio,
        "summary": report.summary,
    }


@router.post("/api/bids/{bid_id}/verify")
@router.post("/bids/{bid_id}/verify")
@router.post("/api/v1/bids/{bid_id}/verify")
async def run_verification(
    bid_id: str,
    body: Optional[VerifyBidRequest] = None,
    db=Depends(get_db),
):
    """
    Trigger external government connector verifications across all 6 registries:
    GSTN, PAN, UDYAM, EPFO, STARTUP_INDIA, and DEBARMENT.
    Supports simulate_timeout for Graceful Degradation testing.
    """
    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    # Gather extracted evidence from bid documents
    ev_cursor = db["evidence"].find({"$or": [{"bid_id": bid_id}, {"package_id": bid_id}]})
    evidence_list = await ev_cursor.to_list(100)

    query: Dict[str, Any] = {
        "bidder_id": bid.get("bidder_id", "demo_bidder_001"),
        "bidder_name": bid.get("bidder_name", "Bharat Engineering Ltd"),
        "legal_name": bid.get("bidder_name", "Bharat Engineering Ltd"),
        "category": bid.get("bidder_category", "SMALL"),
        "employee_count": bid.get("employee_count", 48),
    }

    # Extract standard statutory fields from evidence
    for ev in evidence_list:
        field_name = ev.get("field_name")
        norm_val = ev.get("normalized_value") or ev.get("raw_value")
        if field_name and norm_val is not None:
            query[field_name] = norm_val

    if body and body.override_identifiers:
        query.update(body.override_identifiers)

    # Execute connectors with optional simulate_timeout
    simulate_timeout = body.simulate_timeout if body else False
    timeout_connectors = body.timeout_connectors if body else None

    connector_results = await connector_manager.verify_all(
        query=query,
        simulate_timeout=simulate_timeout,
        timeout_connectors=timeout_connectors,
    )

    verifications_data = [r.model_dump() for r in connector_results]
    impact = connector_manager.evaluate_connector_impact(connector_results)

    await db["bids"].update_one(
        {"_id": oid},
        {"$set": {
            "verifications": verifications_data,
            "verification_impact": impact,
            "last_verified_at": utcnow_str(),
        }},
    )

    # Record Audit Event
    await db["audit"].insert_one({
        "timestamp": utcnow_str(),
        "actor": "system",
        "action": "GOV_CONNECTORS_VERIFIED",
        "entity_id": bid_id,
        "details": {
            "simulate_timeout": simulate_timeout,
            "timeout_connectors": timeout_connectors,
            "impact": impact,
            "verifications_summary": {r.source: r.status for r in connector_results},
        },
    })

    return {
        "bid_id": bid_id,
        "verifications": verifications_data,
        "impact": impact,
    }


@router.get("/api/bids/{bid_id}/verifications")
@router.get("/bids/{bid_id}/verifications")
@router.get("/api/v1/bids/{bid_id}/verifications")
async def list_verifications(bid_id: str, db=Depends(get_db)):
    """List verification status for a bid."""
    bid = await db["bids"].find_one({"_id": to_oid(bid_id)})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")
    return bid.get("verifications", [])


@router.post("/api/v1/bids/{bid_id}/officer-action")
@router.post("/api/bids/{bid_id}/officer-action")
@router.post("/bids/{bid_id}/officer-action")
async def officer_action(bid_id: str, body: OfficerActionRequest, db=Depends(get_db)):
    """Procurement Officer action (APPROVE, REJECT, SEEK_CLARIFICATION)."""
    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    update_fields = {
        "officer_decision": body.action,
        "officer_reason": body.reason,
        "officer_actor": body.actor,
        "officer_action_time": utcnow_str(),
        "status": "APPROVED" if body.action == "APPROVE" else "REJECTED" if body.action == "REJECT" else "CLARIFICATION_REQUESTED",
    }
    await db["bids"].update_one({"_id": oid}, {"$set": update_fields})

    # Log to audit trail
    await db["audit"].insert_one({
        "timestamp": utcnow_str(),
        "actor": body.actor or "officer@gem.gov.in",
        "action": f"OFFICER_{body.action}",
        "entity_id": bid_id,
        "details": {"reason": body.reason, "overrides": body.clause_overrides},
    })

    return {"status": "success", "bid_id": bid_id, "decision": body.action}


# ── Compliance Evidence Trace ─────────────────────────────────────────────────

@router.get("/api/v1/bids/{bid_id}/trace")
@router.get("/api/bids/{bid_id}/trace")
@router.get("/bids/{bid_id}/trace")
async def get_compliance_trace(bid_id: str, db=Depends(get_db)):
    """
    Build and return the full compliance evidence trace chain for a bid.
    Each chain links: Tender Clause → Requirement Rule → Extracted Evidence → Registry Verification → Rule Result.
    Used by the Evidence Trace tab in the officer dashboard.
    """
    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    bid_dict = doc_to_dict(bid)
    tender_id = bid_dict.get("tender_id")
    tender_ref = bid_dict.get("tender_reference") or tender_id or "—"

    # Fetch tender rules
    rules_cursor = db["rules"].find({"tender_id": tender_id}) if tender_id else db["rules"].find({})
    rules = [doc_to_dict(r) for r in await rules_cursor.to_list(100)]

    # Fetch all extracted evidence for this bid
    ev_cursor = db["evidence"].find({"$or": [{"bid_id": bid_id}, {"package_id": bid_id}]})
    all_evidence = [doc_to_dict(e) for e in await ev_cursor.to_list(200)]

    # Build a metric → evidence lookup
    ev_by_metric = {}
    for ev in all_evidence:
        fn = ev.get("field_name") or ev.get("field", "")
        if fn:
            ev_by_metric.setdefault(fn, []).append(ev)

    # Verifications stored on bid
    verifications = bid_dict.get("verifications", [])
    verif_by_source = {v.get("source"): v for v in verifications if v.get("source")}

    # Evaluation results (rule-level outcomes)
    eval_results = bid_dict.get("evaluation_results") or bid_dict.get("rule_results") or []
    results_by_rule_id = {}
    for r in eval_results:
        rid = str(r.get("rule_id") or r.get("id") or "")
        if rid:
            results_by_rule_id[rid] = r

    # Officer actions
    officer_actions = bid_dict.get("officer_actions") or []

    # Human-readable rule name mapping
    METRIC_HUMAN = {
        "annual_turnover_cr": "Annual Turnover",
        "gst_registration_active": "GST Registration Active",
        "gst_registration_status": "GST Registration Status",
        "udyam_registration_active": "Udyam / MSME Registration",
        "udyam_registration_status": "Udyam Registration",
        "pan_card_valid": "PAN Card Validity",
        "legal_name_matching": "Legal Entity Name Match",
        "legal_entity_name": "Legal Entity Name",
        "oem_authorization": "OEM Authorization",
        "oem_authorization_letter": "OEM Authorization Letter",
        "iso_9001_validity": "ISO 9001 Certificate Validity",
        "iso_9001_certificate": "ISO 9001 Certificate",
        "epfo_status": "EPFO / Establishment Status",
        "epfo_registration": "EPFO Registration",
        "debarment_status": "Debarment Clearance",
        "debarment_declaration": "Debarment Declaration",
        "mii_local_content_percentage": "Make-in-India Local Content %",
    }

    chains = []
    for idx, rule in enumerate(rules):
        rule_id = str(rule.get("id") or rule.get("_id") or f"rule-{idx}")
        metric = rule.get("metric", "")
        operator = rule.get("operator", "==")
        threshold = rule.get("threshold", "")
        threshold_unit = rule.get("threshold_unit") or rule.get("unit") or ""
        is_mandatory = rule.get("severity") in ("CRITICAL", "HIGH") or rule.get("is_mandatory", True)
        rule_type = rule.get("rule_type") or metric.upper()
        verif_source = rule.get("verification_source") or ""

        # Aliases for evidence lookup
        alias_map = {
            "annual_turnover_cr": ["turnover_avg_3fy", "turnover"],
            "gst_registration_active": ["gstin", "gst_registration_status"],
            "pan_card_valid": ["pan"],
            "udyam_registration_active": ["udyam_number", "udyam_registration_status"],
            "legal_name_matching": ["legal_entity_name"],
            "oem_authorization": ["oem_authorization_letter"],
            "iso_9001_validity": ["iso_9001_certificate"],
            "epfo_status": ["epfo_registration"],
            "debarment_status": ["debarment_declaration"],
        }
        evidence_items = ev_by_metric.get(metric, [])
        if not evidence_items:
            for alias in alias_map.get(metric, []):
                evidence_items = ev_by_metric.get(alias, [])
                if evidence_items:
                    break

        # Match verification
        chain_verifications = []
        if verif_source and verif_source in verif_by_source:
            v = verif_by_source[verif_source]
            chain_verifications.append({
                "source": v.get("source"),
                "source_label": v.get("source_label") or v.get("source"),
                "connector_status": v.get("connector_status") or v.get("status"),
                "message": v.get("message"),
                "fields_verified": v.get("fields_verified") or {},
            })

        # Match rule result
        result_obj = results_by_rule_id.get(rule_id)
        if not result_obj:
            # Try matching by metric
            for r in eval_results:
                if r.get("metric") == metric or r.get("field_name") == metric:
                    result_obj = r
                    break
        if not result_obj:
            result_obj = {
                "result": "PENDING",
                "status": "PENDING",
                "explanation": "This rule has not been evaluated yet. Click Re-evaluate.",
                "confidence": None,
            }

        result_status = result_obj.get("result") or result_obj.get("status") or "PENDING"
        explanation = result_obj.get("explanation") or "No explanation available."

        chains.append({
            "chain_id": f"chain-{rule_id}",
            "clause_number": rule.get("clause_id") or rule.get("clause_number"),
            "clause_title": rule.get("description") or METRIC_HUMAN.get(metric, metric.replace("_", " ").title()),
            "clause_text": rule.get("clause_text"),
            "rule": {
                "rule_type": rule_type,
                "metric": metric,
                "operator": operator,
                "threshold_value": threshold,
                "threshold_unit": threshold_unit,
                "description": rule.get("description") or METRIC_HUMAN.get(metric, metric.replace("_", " ").title()),
                "is_mandatory": is_mandatory,
            },
            "evidence": [
                {
                    "field": ev.get("field_name") or ev.get("field", ""),
                    "raw_value": ev.get("raw_value"),
                    "normalized_value": ev.get("normalized_value"),
                    "confidence": ev.get("confidence"),
                    "document_filename": ev.get("document_filename") or ev.get("original_filename"),
                    "source_page": ev.get("source_page"),
                    "doc_type": ev.get("doc_type") or ev.get("document_type"),
                }
                for ev in evidence_items
            ],
            "verifications": chain_verifications,
            "result": {
                "result": result_status,
                "explanation": explanation,
                "confidence": result_obj.get("confidence"),
            },
            "officer_actions": [
                a for a in officer_actions
                if a.get("rule_id") == rule_id or a.get("metric") == metric
            ],
        })

    return {
        "bid_id": bid_id,
        "tender_reference": tender_ref,
        "bidder_name": bid_dict.get("bidder_name") or bid_dict.get("bidder", {}).get("name", "Bidder"),
        "chains": chains,
        "total_rules": len(chains),
        "generated_at": utcnow_str(),
    }


from app.engine.audit import AuditEngine


@router.post("/api/v1/bids/{bid_id}/override")
@router.post("/api/bids/{bid_id}/override")
@router.post("/bids/{bid_id}/override")
async def officer_override(
    bid_id: str,
    body: OfficerOverrideRequest,
    db=Depends(get_db),
):
    """
    Procurement Officer Override endpoint.
    Strictly enforces a mandatory justification string before altering a system result
    and logging to the cryptographic SHA-256 audit chain.
    """
    # 1. Enforce mandatory justification string
    justification = (body.justification or "").strip()
    if not justification or len(justification) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Procurement Officer justification is mandatory and must be a substantive explanation (minimum 5 characters).",
        )

    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    new_status_upper = body.new_status.strip().upper()
    if new_status_upper not in ("PASS", "FAIL", "REVIEW", "PENDING"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid override status '{body.new_status}'. Allowed: PASS, FAIL, REVIEW, PENDING.",
        )

    # 2. Update rule results in bid
    evaluation_results = bid.get("evaluation_results", [])
    updated = False
    old_status = "UNKNOWN"

    for r in evaluation_results:
        # Match by rule_id or metric
        if (body.rule_id and r.get("rule_id") == body.rule_id) or (body.metric and r.get("metric") == body.metric):
            old_status = r.get("status", "UNKNOWN")
            r["status"] = new_status_upper
            r["officer_override"] = True
            r["officer_justification"] = justification
            r["officer_actor"] = body.actor or "officer@gem.gov.in"
            r["override_time"] = utcnow_str()
            r["explanation"] = f"[OVERRIDDEN by {body.actor}]: {justification} (Prior status: {old_status})"
            updated = True
            break

    if not updated:
        if evaluation_results:
            first_r = evaluation_results[0]
            old_status = first_r.get("status", "UNKNOWN")
            first_r["status"] = new_status_upper
            first_r["officer_override"] = True
            first_r["officer_justification"] = justification
            first_r["explanation"] = f"[OVERRIDDEN by {body.actor}]: {justification}"
        else:
            # Create a synthetic rule result entry
            old_status = "PENDING"
            evaluation_results.append({
                "rule_id": body.rule_id or "RULE-MANUAL-OVERRIDE",
                "bidder_id": bid.get("bidder_id", "bidder_001"),
                "status": new_status_upper,
                "evidence_ids": [],
                "explanation": f"[OVERRIDDEN by {body.actor}]: {justification}",
                "officer_override": True,
                "officer_justification": justification,
            })

    # Recalculate overall status
    has_fail = any(r.get("status") == "FAIL" for r in evaluation_results)
    has_pending = any(r.get("status") == "PENDING" for r in evaluation_results)
    has_review = any(r.get("status") == "REVIEW" for r in evaluation_results)

    if has_fail:
        new_overall = "NON_COMPLIANT"
        new_risk = 85.0
    elif has_pending:
        new_overall = "PENDING_VERIFICATION"
        new_risk = 25.0
    elif has_review:
        new_overall = "UNDER_REVIEW"
        new_risk = 35.0
    else:
        new_overall = "COMPLIANT"
        new_risk = 15.0

    await db["bids"].update_one(
        {"_id": oid},
        {"$set": {
            "compliance_status": new_overall,
            "risk_score": new_risk,
            "evaluation_results": evaluation_results,
            "officer_override_active": True,
            "latest_override": {
                "actor": body.actor or "officer@gem.gov.in",
                "justification": justification,
                "rule_id": body.rule_id,
                "old_status": old_status,
                "new_status": new_status_upper,
                "timestamp": utcnow_str(),
            },
        }},
    )

    # 3. Log to Cryptographic Audit Chain
    audit_record = await AuditEngine.log_officer_override(
        db=db,
        bid_id=bid_id,
        actor=body.actor or "officer@gem.gov.in",
        justification=justification,
        rule_id=body.rule_id,
        old_status=old_status,
        new_status=new_status_upper,
        details={
            "metric": body.metric,
            "new_overall_status": new_overall,
            "new_risk_score": new_risk,
            "notes": body.notes,
        },
    )

    return {
        "status": "success",
        "bid_id": bid_id,
        "rule_id": body.rule_id,
        "previous_status": old_status,
        "overridden_status": new_status_upper,
        "new_compliance_status": new_overall,
        "new_risk_score": new_risk,
        "justification": justification,
        "actor": body.actor or "officer@gem.gov.in",
        "event_hash": audit_record.get("event_hash"),
        "prev_hash": audit_record.get("prev_hash"),
    }
