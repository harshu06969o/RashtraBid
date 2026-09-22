"""
GeM-Guard — Tenders Router
Strict Specifications:
1. PDF Ingestion: POST /api/v1/tenders/upload utilizing PyMuPDF to parse text and table structures.
2. Rule Extraction: Integrates TenderCompiler to extract financial turnover, MII %, and statutory registrations.
3. Manual Override: PUT /api/v1/tenders/{id}/rules allowing Procurement Officer to modify/add rules.
4. Flexible Lookup: Supports querying tenders by _id, id, tender_no, and reference_number.
5. Bidder Synchronization: Tenders created and published are permanently saved in MongoDB and visible to bidders.
"""

import logging
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.core.database import doc_to_dict, get_db, safe_oid, to_oid, utcnow_str
from app.core.storage import storage
from app.schemas.domain import AuditEvent, RequirementRule, Tender
from app.pipeline.tender_compiler import TenderCompiler

logger = logging.getLogger("gemguard.routers.tenders")

router = APIRouter(tags=["tenders"])


class TenderCreateRequest(BaseModel):
    tender_no: Optional[str] = None
    reference_number: Optional[str] = None
    title: str
    organization: Optional[str] = "CPCL"
    buyer: Optional[str] = "CPCL"
    authority: Optional[str] = None
    description: Optional[str] = None
    closing_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    turnover_threshold_cr: Optional[float] = None
    estimated_value_cr: Optional[float] = None
    local_content_pct: Optional[float] = None
    category: Optional[str] = "Goods"
    status: Optional[str] = "ACTIVE"


class CompileRulesRequest(BaseModel):
    source: Optional[str] = "pattern"  # "ai" or "pattern"


class RuleOverrideItem(BaseModel):
    id: Optional[str] = None
    clause_id: Optional[str] = None
    metric: str
    operator: str
    threshold: Any
    unit: Optional[str] = ""
    severity: Optional[str] = "CRITICAL"
    conditions: Optional[Dict[str, Any]] = None
    evidence_type: Optional[str] = None
    verification_source: Optional[str] = None
    clause_text: Optional[str] = None


class ManualRulesOverrideRequest(BaseModel):
    rules: List[RuleOverrideItem]
    actor: Optional[str] = "officer@gem.gov.in"
    reason: Optional[str] = "Manual rule adjustment by Procurement Officer"


# ── Tenders CRUD ─────────────────────────────────────────────────────────────

@router.get("/api/v1/tenders")
@router.get("/api/tenders")
@router.get("/tenders")
async def list_tenders(db=Depends(get_db)):
    """List all tenders ordered by creation time, populated with their requirement rules."""
    cursor = db["tenders"].find().sort("created_at", -1)
    docs = await cursor.to_list(100)
    results = []
    for d in docs:
        tender_dict = doc_to_dict(d)
        t_id = tender_dict.get("id")
        ref_no = tender_dict.get("reference_number") or tender_dict.get("tender_no")

        # Fetch associated rules from rules collection
        rule_query = []
        if t_id:
            rule_query.append({"tender_id": t_id})
        if ref_no:
            rule_query.append({"tender_id": ref_no})
            rule_query.append({"tender_no": ref_no})

        rules_list = []
        if rule_query:
            rules_cursor = db["rules"].find({"$or": rule_query})
            rules_list = [doc_to_dict(r) for r in await rules_cursor.to_list(100)]

        # If rules exist in collection use them; otherwise check embedded rules
        tender_dict["requirement_rules"] = rules_list or tender_dict.get("requirement_rules") or []
        tender_dict["rules"] = tender_dict["requirement_rules"]
        results.append(tender_dict)

    return results


@router.get("/api/v1/tenders/{tender_id}")
@router.get("/api/tenders/{tender_id}")
@router.get("/tenders/{tender_id}")
async def get_tender(tender_id: str, db=Depends(get_db)):
    """Get single tender details by ID, tender_no, or reference_number."""
    oid = safe_oid(tender_id)
    query = [{"_id": oid}] if oid else []
    query.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    t = await db["tenders"].find_one({"$or": query})
    if not t:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    res = doc_to_dict(t)
    t_id = res.get("id")
    ref_no = res.get("reference_number") or res.get("tender_no")

    rule_query = []
    if t_id:
        rule_query.append({"tender_id": t_id})
    if ref_no:
        rule_query.append({"tender_id": ref_no})
        rule_query.append({"tender_no": ref_no})

    rules_list = []
    if rule_query:
        rules_cursor = db["rules"].find({"$or": rule_query})
        rules_list = [doc_to_dict(r) for r in await rules_cursor.to_list(100)]

    res["requirement_rules"] = rules_list or res.get("requirement_rules") or []
    res["rules"] = res["requirement_rules"]
    return res


@router.post("/api/v1/tenders", status_code=status.HTTP_201_CREATED)
@router.post("/api/tenders", status_code=status.HTTP_201_CREATED)
@router.post("/tenders", status_code=status.HTTP_201_CREATED)
async def create_tender(body: TenderCreateRequest, db=Depends(get_db)):
    """Create a new tender and persist to MongoDB."""
    ref_no = (body.reference_number or body.tender_no or "").strip()
    if not ref_no:
        ref_no = f"GEM/2026/B/{secrets.token_hex(4).upper()}"

    org = body.authority or body.organization or body.buyer or "CPCL"
    turnover_cr = body.turnover_threshold_cr if body.turnover_threshold_cr is not None else 10.0
    mii_pct = body.local_content_pct if body.local_content_pct is not None else 50.0

    payload = {
        "tender_no": ref_no,
        "reference_number": ref_no,
        "title": body.title.strip(),
        "organization": org,
        "buyer": org,
        "authority": org,
        "description": body.description or f"Procurement of {body.title.strip()}",
        "closing_date": body.closing_date,
        "submission_deadline": body.submission_deadline or body.closing_date,
        "turnover_threshold_cr": turnover_cr,
        "estimated_value_cr": body.estimated_value_cr or 0.0,
        "local_content_pct": mii_pct,
        "local_content_threshold_pct": mii_pct,
        "category": body.category or "Goods",
        "status": body.status or "ACTIVE",
        "created_at": utcnow_str(),
        "updated_at": utcnow_str(),
        "version": 1,
        "documents": [],
    }

    # Check for existing tender by reference number
    existing = await db["tenders"].find_one({"$or": [{"tender_no": ref_no}, {"reference_number": ref_no}]})
    if existing:
        target_id = str(existing["_id"])
        await db["tenders"].update_one({"_id": existing["_id"]}, {"$set": payload})
        created = await db["tenders"].find_one({"_id": existing["_id"]})
    else:
        result = await db["tenders"].insert_one(payload)
        target_id = str(result.inserted_id)
        created = await db["tenders"].find_one({"_id": result.inserted_id})

    # Create baseline requirement rules if not already present
    existing_rules = await db["rules"].count_documents({"tender_id": target_id})
    if existing_rules == 0:
        baseline_rules = [
            {
                "tender_id": target_id,
                "clause_id": "Clause 3.1",
                "metric": "annual_turnover_cr",
                "operator": ">=",
                "threshold": turnover_cr,
                "unit": "INR_CR",
                "severity": "CRITICAL",
                "clause_text": f"Minimum average annual turnover threshold of INR {turnover_cr} Crores during preceding 3 financial years.",
                "evidence_type": "CA_CERTIFICATE",
                "verification_source": "GSTN",
                "created_at": utcnow_str(),
                "source": "OFFICER_INPUT",
            },
            {
                "tender_id": target_id,
                "clause_id": "Clause 3.4",
                "metric": "mii_local_content_percentage",
                "operator": ">=",
                "threshold": mii_pct,
                "unit": "%",
                "severity": "HIGH",
                "clause_text": f"Bidder shall qualify as a local supplier with minimum {mii_pct}% local content as per PPP-MII order.",
                "evidence_type": "MII_DECLARATION",
                "verification_source": "DPIIT",
                "created_at": utcnow_str(),
                "source": "OFFICER_INPUT",
            },
            {
                "tender_id": target_id,
                "clause_id": "Clause 3.2",
                "metric": "gst_registration_active",
                "operator": "==",
                "threshold": True,
                "unit": "BOOLEAN",
                "severity": "CRITICAL",
                "clause_text": "Goods and Services Tax (GST) registration status must be ACTIVE as of bid submission date.",
                "evidence_type": "GST_CERTIFICATE",
                "verification_source": "GSTN",
                "created_at": utcnow_str(),
                "source": "BASELINE",
            },
            {
                "tender_id": target_id,
                "clause_id": "Clause 3.5",
                "metric": "pan_card_valid",
                "operator": "==",
                "threshold": True,
                "unit": "BOOLEAN",
                "severity": "CRITICAL",
                "clause_text": "Permanent Account Number (PAN) card must be valid and verified with Income Tax Department.",
                "evidence_type": "PAN_CARD",
                "verification_source": "INCOME_TAX_PAN",
                "created_at": utcnow_str(),
                "source": "BASELINE",
            },
            {
                "tender_id": target_id,
                "clause_id": "Clause 3.3",
                "metric": "udyam_registration_active",
                "operator": "==",
                "threshold": True,
                "unit": "BOOLEAN",
                "severity": "MEDIUM",
                "clause_text": "Valid Udyam Registration Certificate for MSME bidders claiming purchase preference.",
                "evidence_type": "UDYAM_CERTIFICATE",
                "verification_source": "UDYAM",
                "created_at": utcnow_str(),
                "source": "BASELINE",
            },
        ]
        clean_rules = []
        for r in baseline_rules:
            res_r = await db["rules"].insert_one(r)
            r_dict = dict(r)
            r_dict["id"] = str(res_r.inserted_id)
            r_dict.pop("_id", None)
            clean_rules.append(r_dict)

        await db["tenders"].update_one(
            {"_id": created["_id"]},
            {"$set": {"requirement_rules": clean_rules}},
        )
        created["requirement_rules"] = clean_rules

    # Audit log
    await db["audit"].insert_one({
        "timestamp": utcnow_str(),
        "actor": "officer@gem.gov.in",
        "action": "TENDER_CREATED",
        "entity_id": target_id,
        "details": {"tender_no": ref_no, "title": body.title.strip()},
    })

    created_dict = doc_to_dict(created)
    created_dict["requirement_rules"] = [doc_to_dict(r) for r in created.get("requirement_rules", [])]
    created_dict["rules"] = created_dict["requirement_rules"]
    return created_dict


@router.put("/api/v1/tenders/{tender_id}")
@router.put("/api/tenders/{tender_id}")
@router.put("/tenders/{tender_id}")
async def update_tender(tender_id: str, body: Dict[str, Any], db=Depends(get_db)):
    """Update tender metadata by ID, tender_no, or reference_number."""
    oid = safe_oid(tender_id)
    query = [{"_id": oid}] if oid else []
    query.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    body.pop("_id", None)
    body.pop("id", None)
    body["updated_at"] = utcnow_str()

    res = await db["tenders"].update_one({"$or": query}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    updated = await db["tenders"].find_one({"$or": query})
    res_dict = doc_to_dict(updated)

    # Fetch updated rules
    t_id = res_dict.get("id")
    ref_no = res_dict.get("reference_number") or res_dict.get("tender_no")
    rule_query = []
    if t_id:
        rule_query.append({"tender_id": t_id})
    if ref_no:
        rule_query.append({"tender_id": ref_no})
    rules_docs = await db["rules"].find({"$or": rule_query}).to_list(100) if rule_query else []
    res_dict["requirement_rules"] = [doc_to_dict(r) for r in rules_docs] or res_dict.get("requirement_rules", [])
    res_dict["rules"] = res_dict["requirement_rules"]
    return res_dict


@router.delete("/api/v1/tenders/{tender_id}")
@router.delete("/api/tenders/{tender_id}")
@router.delete("/tenders/{tender_id}")
async def delete_tender(tender_id: str, db=Depends(get_db)):
    """
    Permanently delete a tender and cascade delete associated rules, bids, documents, and evidence from MongoDB.
    """
    oid = safe_oid(tender_id)
    query = [{"_id": oid}] if oid else []
    query.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    tender = await db["tenders"].find_one({"$or": query})
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    t_id = str(tender["_id"])
    ref_no = tender.get("reference_number") or tender.get("tender_no")

    # IDs to match in cascades
    ids_to_clean = [t_id, str(tender.get("id", ""))]
    if ref_no:
        ids_to_clean.append(ref_no)
    ids_to_clean = [i for i in ids_to_clean if i]

    # Delete tender
    await db["tenders"].delete_one({"_id": tender["_id"]})

    # Cascade delete associated rules
    await db["rules"].delete_many({"tender_id": {"$in": ids_to_clean}})

    # Find and delete associated bids & bid documents
    bids_cursor = db["bids"].find({"$or": [
        {"tender_id": {"$in": ids_to_clean}},
        {"tender_reference": {"$in": ids_to_clean}},
    ]})
    associated_bids = await bids_cursor.to_list(200)
    bid_ids = [str(b["_id"]) for b in associated_bids] + [b.get("id") for b in associated_bids if b.get("id")]
    bid_ids = [i for i in bid_ids if i]

    if bid_ids:
        bid_oids = [to_oid(b) for b in bid_ids if to_oid(b)]
        await db["bids"].delete_many({"$or": [{"_id": {"$in": bid_oids}}, {"id": {"$in": bid_ids}}]})
        await db["bid_documents"].delete_many({"bid_id": {"$in": bid_ids}})
        await db["evidence"].delete_many({"$or": [{"bid_id": {"$in": bid_ids}}, {"package_id": {"$in": bid_ids}}]})

    # Delete tender documents
    await db["documents"].delete_many({"tender_id": {"$in": ids_to_clean}})

    # Audit event
    await db["audit"].insert_one({
        "timestamp": utcnow_str(),
        "actor": "officer@gem.gov.in",
        "action": "TENDER_DELETED",
        "entity_id": t_id,
        "details": {
            "reference_number": ref_no,
            "title": tender.get("title"),
            "deleted_bids_count": len(associated_bids),
        },
    })

    return {
        "status": "success",
        "message": f"Tender {ref_no or t_id} and associated resources deleted successfully",
        "deleted_tender_id": t_id,
        "deleted_bids_count": len(associated_bids),
    }



@router.get("/api/v1/tenders/{tender_id}/bids")
@router.get("/api/tenders/{tender_id}/bids")
@router.get("/tenders/{tender_id}/bids")
async def get_tender_bids(tender_id: str, db=Depends(get_db)):
    """Get all submitted bids for a specific tender."""
    oid = safe_oid(tender_id)
    tender_query = [{"_id": oid}] if oid else []
    tender_query.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    tender = await db["tenders"].find_one({"$or": tender_query})

    match_keys = [tender_id]
    if tender:
        if "_id" in tender:
            match_keys.append(str(tender["_id"]))
        if "id" in tender and tender["id"]:
            match_keys.append(str(tender["id"]))
        if "tender_no" in tender and tender["tender_no"]:
            match_keys.append(str(tender["tender_no"]))
        if "reference_number" in tender and tender["reference_number"]:
            match_keys.append(str(tender["reference_number"]))

    unique_keys = list(set(match_keys))
    cursor = db["bids"].find({
        "$or": [
            {"tender_id": {"$in": unique_keys}},
            {"tender_reference": {"$in": unique_keys}},
        ]
    }).sort("created_at", -1)
    bids = await cursor.to_list(100)
    return [doc_to_dict(b) for b in bids]


# ── Specification 1 & 2: PDF Ingestion & Rule Compilation ────────────────────

@router.post("/api/v1/tenders/upload")
@router.post("/api/tenders/upload")
@router.post("/tenders/upload")
async def upload_and_compile_tender(
    file: UploadFile = File(...),
    tender_id: Optional[str] = Form(None),
    db=Depends(get_db),
):
    """
    Ingest tender PDF via PyMuPDF (capturing text and table structures).
    Validates document authenticity:
    - If valid tender: extracts RequirementRules and persists to MongoDB.
    - If not a tender (e.g. resume or receipt): rejects rule generation and returns diagnostic warning.
    """
    # 1. Read file bytes and save to hybrid storage
    file_bytes = await file.read()
    stored = await storage.save_file(
        file_input=file_bytes,
        filename=file.filename,
        subfolder="tenders",
        content_type=file.content_type,
    )

    # 2. Run Tender AI Compiler (PyMuPDF parser with tables + Rule Extraction Engine)
    metadata, extracted_rules, diagnostics = TenderCompiler.compile_pdf(
        pdf_input=file_bytes,
        tender_id=tender_id,
    )

    target_tender_id = tender_id
    tender_doc = None

    # 3. Locate existing tender if tender_id was supplied
    if target_tender_id:
        oid = safe_oid(target_tender_id)
        query = [{"_id": oid}] if oid else []
        query.extend([
            {"_id": target_tender_id},
            {"id": target_tender_id},
            {"tender_no": target_tender_id},
            {"reference_number": target_tender_id},
        ])
        tender_doc = await db["tenders"].find_one({"$or": query})
        if tender_doc:
            target_tender_id = str(tender_doc["_id"])

    # If no existing tender was found, create or match by detected reference number
    if not tender_doc:
        detected_no = metadata.get("tender_no") or f"GEM/2026/B/{stored.file_hash[:7].upper()}"
        existing = await db["tenders"].find_one({
            "$or": [{"tender_no": detected_no}, {"reference_number": detected_no}]
        })
        if existing:
            target_tender_id = str(existing["_id"])
            tender_doc = existing
        else:
            doc_title = metadata.get("title") or Path(file.filename).stem.replace("_", " ").title()
            new_tender = {
                "tender_no": detected_no,
                "reference_number": detected_no,
                "title": doc_title,
                "organization": metadata.get("organization") or "CPCL",
                "buyer": metadata.get("organization") or "CPCL",
                "authority": metadata.get("organization") or "CPCL",
                "closing_date": metadata.get("closing_date"),
                "file_hash": stored.file_hash,
                "document_path": str(stored.file_path),
                "filename": stored.filename,
                "status": "ACTIVE",
                "version": 1,
                "created_at": utcnow_str(),
                "updated_at": utcnow_str(),
                "documents": [],
            }
            res = await db["tenders"].insert_one(new_tender)
            target_tender_id = str(res.inserted_id)
            tender_doc = await db["tenders"].find_one({"_id": res.inserted_id})

    # Prepare document metadata record
    new_doc_entry = {
        "id": f"doc-{stored.file_hash[:10]}",
        "original_filename": file.filename,
        "filename": stored.filename,
        "file_size": len(file_bytes),
        "file_hash": stored.file_hash,
        "uploaded_at": utcnow_str(),
        "uploaded_by": "officer@gem.gov.in",
        "document_path": str(stored.file_path),
    }

    # Update tender record with file metadata and append document entry
    await db["tenders"].update_one(
        {"_id": tender_doc["_id"]},
        {
            "$set": {
                "file_hash": stored.file_hash,
                "document_path": str(stored.file_path),
                "filename": stored.filename,
                "updated_at": utcnow_str(),
            },
            "$push": {"documents": new_doc_entry},
        },
    )

    # 4. Check domain validity
    is_valid_tender = diagnostics.get("is_tender", True)

    saved_rules = []
    if is_valid_tender and extracted_rules:
        # Clear existing auto-compiled rules for this tender (preserving manual overrides)
        await db["rules"].delete_many({"tender_id": target_tender_id, "is_manual": {"$ne": True}})

        for r in extracted_rules:
            r.tender_id = target_tender_id
            r_dict = r.model_dump(by_alias=True, exclude_none=True)
            r_dict.pop("id", None)
            r_dict.pop("_id", None)
            r_dict["created_at"] = utcnow_str()
            r_dict["source"] = "AI_COMPILER"
            insert_res = await db["rules"].insert_one(r_dict)
            r_dict["id"] = str(insert_res.inserted_id)
            r_dict.pop("_id", None)
            saved_rules.append(r_dict)

        # Embed compiled rules in the tender document
        await db["tenders"].update_one(
            {"_id": tender_doc["_id"]},
            {"$set": {"requirement_rules": saved_rules}},
        )

    # 5. Log audit event
    await db["audit"].insert_one({
        "timestamp": utcnow_str(),
        "actor": "officer@gem.gov.in",
        "action": "TENDER_PDF_INGESTED",
        "entity_id": target_tender_id,
        "details": {
            "filename": stored.filename,
            "file_hash": stored.file_hash,
            "is_tender": is_valid_tender,
            "rules_count": len(saved_rules),
            "diagnostics": diagnostics,
        },
    })

    refreshed_tender = await db["tenders"].find_one({"_id": tender_doc["_id"]})
    tender_response = doc_to_dict(refreshed_tender)
    clean_saved = [doc_to_dict(r) for r in saved_rules]
    tender_response["requirement_rules"] = clean_saved or tender_response.get("requirement_rules", [])
    tender_response["rules"] = tender_response["requirement_rules"]

    if not is_valid_tender:
        return {
            "status": "warning",
            "is_tender": False,
            "message": f"Uploaded PDF does not appear to be an official Tender or RFP document ({diagnostics.get('detection_reason', 'No procurement keywords detected')}). No rules were extracted.",
            "tender": tender_response,
            "rules": [],
            "diagnostics": diagnostics,
        }

    return {
        "status": "success",
        "is_tender": True,
        "message": f"Successfully parsed tender PDF and compiled {len(saved_rules)} compliance rules.",
        "tender": tender_response,
        "rules": clean_saved,
        "diagnostics": diagnostics,
    }


# Also maintain tender_id-scoped upload for backwards compatibility
@router.post("/api/v1/tenders/{tender_id}/upload")
@router.post("/api/tenders/{tender_id}/upload")
@router.post("/tenders/{tender_id}/upload")
async def upload_tender_document_scoped(
    tender_id: str,
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """Scoped tender upload routing directly to upload_and_compile_tender."""
    return await upload_and_compile_tender(file=file, tender_id=tender_id, db=db)


@router.get("/api/v1/tenders/{tender_id}/pdf")
@router.get("/api/tenders/{tender_id}/pdf")
@router.get("/tenders/{tender_id}/pdf")
async def get_tender_pdf(
    tender_id: str,
    token: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """Serve the actual PDF document uploaded for a tender.
    Accepts ?token= query param so browser <iframe> and <a download> work.
    """
    import os
    from jose import JWTError, jwt as jose_jwt
    # Validate token if provided via query param (browser iframe/download link)
    if token:
        jwt_secret = os.getenv("JWT_SECRET", "sih_26100_supersecret")
        try:
            jose_jwt.decode(token, jwt_secret, algorithms=["HS256"])
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    oid = safe_oid(tender_id)
    query = [{"_id": oid}] if oid else []
    query.extend([{"_id": tender_id}, {"id": tender_id}, {"tender_no": tender_id}, {"reference_number": tender_id}])
    tender = await db["tenders"].find_one({"$or": query})
    if not tender or (not tender.get("document_path") and not tender.get("url")):
        raise HTTPException(status_code=404, detail="Tender or PDF document not found")

    url = tender.get("url")
    path = Path(tender.get("document_path") or "")
    if not path.exists():
        if url and url.startswith("http"):
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=url)
        # Fallback for missing local files (e.g. demo data or ephemeral wipe)
        from fastapi.responses import Response
        dummy_pdf = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Resources <<\n/Font <<\n/F1 4 0 R\n>>\n>>\n/Contents 5 0 R\n>>\nendobj\n4 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n5 0 obj\n<<\n/Length 75\n>>\nstream\nBT\n/F1 12 Tf\n10 750 Td\n(This file was lost or not found on the local ephemeral disk.) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000219 00000 n\n0000000307 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n433\n%%EOF"
        return Response(content=dummy_pdf, media_type="application/pdf")

    from fastapi.responses import FileResponse
    original_name = tender.get("original_filename") or tender.get("filename", "tender.pdf")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=original_name,
        headers={"Content-Disposition": f'inline; filename="{original_name}"'},
    )

@router.put("/api/v1/tenders/{tender_id}/rules")
@router.put("/api/tenders/{tender_id}/rules")
@router.put("/tenders/{tender_id}/rules")
async def manual_rule_override(
    tender_id: str,
    body: Union[ManualRulesOverrideRequest, List[Dict[str, Any]], Dict[str, Any]],
    db=Depends(get_db),
):
    """
    Manual Override: Allows Procurement Officer to manually modify or add rules.
    - Validates inputs using RequirementRule domain model.
    - Updates/replaces rules for the tender in db['rules'] and embeds in db['tenders'].
    - Emits tamper-evident AuditEvent with SHA-256 hash.
    """
    oid = safe_oid(tender_id)
    query = [{"_id": oid}] if oid else []
    query.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    tender = await db["tenders"].find_one({"$or": query})
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    resolved_id = str(tender["_id"])

    # Normalize request structure
    raw_rules: List[Dict[str, Any]] = []
    actor = "officer@gem.gov.in"
    reason = "Procurement Officer manual rule override"

    if isinstance(body, ManualRulesOverrideRequest):
        raw_rules = [r.model_dump() for r in body.rules]
        actor = body.actor or actor
        reason = body.reason or reason
    elif isinstance(body, list):
        raw_rules = body
    elif isinstance(body, dict):
        raw_rules = body.get("rules", [])
        actor = body.get("actor", actor)
        reason = body.get("reason", reason)

    if not raw_rules:
        raise HTTPException(status_code=400, detail="Rules list cannot be empty.")

    # Validate each rule with RequirementRule domain model
    validated_rules: List[Dict[str, Any]] = []
    for idx, r_data in enumerate(raw_rules):
        try:
            r_data["tender_id"] = resolved_id
            rule_obj = RequirementRule(**r_data)
            clean_dict = rule_obj.model_dump(by_alias=True, exclude_none=True)
            clean_dict.pop("id", None)
            clean_dict.pop("_id", None)
            clean_dict["tender_id"] = resolved_id
            clean_dict["is_manual"] = True
            clean_dict["updated_at"] = utcnow_str()
            clean_dict["override_actor"] = actor
            validated_rules.append(clean_dict)
        except Exception as val_err:
            raise HTTPException(
                status_code=422,
                detail=f"Validation failed for rule at index {idx}: {val_err}",
            )

    # Replace existing rules for this tender
    await db["rules"].delete_many({"$or": [{"tender_id": resolved_id}, {"tender_id": tender_id}]})

    # Insert validated rules
    for r in validated_rules:
        await db["rules"].insert_one(r)

    updated_rules = await db["rules"].find({"tender_id": resolved_id}).to_list(100)

    # Embed updated rules in the tender document
    await db["tenders"].update_one(
        {"_id": tender["_id"]},
        {"$set": {"requirement_rules": [doc_to_dict(r) for r in updated_rules]}},
    )

    # Fetch previous hash for audit chain
    latest_audit = await db["audit"].find_one(sort=[("timestamp", -1)])
    prev_hash = latest_audit.get("event_hash") if latest_audit else "GENESIS"

    # Log cryptographic AuditEvent
    audit_event = AuditEvent(
        actor=actor,
        action="OFFICER_RULE_OVERRIDE",
        entity_id=resolved_id,
        prev_hash=prev_hash,
        details={
            "reason": reason,
            "rules_count": len(updated_rules),
            "metrics": [r.get("metric") for r in updated_rules],
        },
    )
    audit_dict = audit_event.model_dump(by_alias=True, exclude_none=True)
    audit_dict.pop("id", None)
    audit_dict.pop("_id", None)
    await db["audit"].insert_one(audit_dict)

    logger.info(
        "Officer %s overridden rules for tender %s (%d rules updated). Audit hash: %s",
        actor,
        resolved_id,
        len(updated_rules),
        audit_dict.get("event_hash", "")[:12],
    )

    return {
        "status": "success",
        "message": f"Successfully updated {len(updated_rules)} rules for tender {tender_id}.",
        "tender_id": resolved_id,
        "rules": [doc_to_dict(r) for r in updated_rules],
        "audit_event_hash": audit_dict.get("event_hash"),
    }


# ── Legacy Compilation Endpoint ──────────────────────────────────────────────

@router.post("/api/v1/tenders/{tender_id}/compile")
@router.post("/api/tenders/{tender_id}/compile")
@router.post("/tenders/{tender_id}/compile")
async def compile_tender_rules(
    tender_id: str,
    body: Optional[CompileRulesRequest] = None,
    db=Depends(get_db),
):
    """Compile rules for an existing tender using TenderCompiler."""
    oid = safe_oid(tender_id)
    query = [{"_id": oid}] if oid else []
    query.extend([
        {"_id": tender_id},
        {"id": tender_id},
        {"tender_no": tender_id},
        {"reference_number": tender_id},
    ])
    tender = await db["tenders"].find_one({"$or": query})
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    resolved_id = str(tender["_id"])
    existing_rules = await db["rules"].find({"tender_id": resolved_id}).to_list(100)
    if existing_rules:
        return {
            "status": "compiled",
            "tender_id": resolved_id,
            "rules_count": len(existing_rules),
            "rules": [doc_to_dict(r) for r in existing_rules],
        }

    # If document path exists, compile from PDF
    doc_path = tender.get("document_path")
    if doc_path and Path(doc_path).exists():
        _, rules, diag = TenderCompiler.compile_pdf(doc_path, tender_id=resolved_id)
        for r in rules:
            r_dict = r.model_dump(by_alias=True, exclude_none=True)
            r_dict.pop("id", None)
            r_dict.pop("_id", None)
            r_dict["created_at"] = utcnow_str()
            await db["rules"].insert_one(r_dict)
    else:
        # Generate baseline standard rules
        default_rules = [
            RequirementRule(
                tender_id=resolved_id,
                clause_id="Clause 3.1",
                metric="annual_turnover_cr",
                operator=">=",
                threshold=tender.get("turnover_threshold_cr", 10.0) or 10.0,
                unit="INR_CR",
                severity="CRITICAL",
                evidence_type="CA_CERTIFICATE",
                verification_source="GSTN",
            ),
            RequirementRule(
                tender_id=resolved_id,
                clause_id="Clause 3.4",
                metric="mii_local_content_percentage",
                operator=">=",
                threshold=tender.get("local_content_pct", 50.0) or 50.0,
                unit="%",
                severity="HIGH",
                evidence_type="MII_DECLARATION",
                verification_source="DPIIT",
            ),
            RequirementRule(
                tender_id=resolved_id,
                clause_id="Clause 3.2",
                metric="gst_registration_active",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                evidence_type="GST_CERTIFICATE",
                verification_source="GSTN",
            ),
            RequirementRule(
                tender_id=resolved_id,
                clause_id="Clause 3.5",
                metric="pan_card_valid",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="CRITICAL",
                evidence_type="PAN_CARD",
                verification_source="INCOME_TAX_PAN",
            ),
            RequirementRule(
                tender_id=resolved_id,
                clause_id="Clause 3.3",
                metric="udyam_registration_active",
                operator="==",
                threshold=True,
                unit="BOOLEAN",
                severity="MEDIUM",
                evidence_type="UDYAM_CERTIFICATE",
                verification_source="UDYAM",
            ),
        ]
        for r in default_rules:
            r_dict = r.model_dump(by_alias=True, exclude_none=True)
            r_dict.pop("id", None)
            r_dict.pop("_id", None)
            r_dict["created_at"] = utcnow_str()
            await db["rules"].insert_one(r_dict)

    saved_rules = await db["rules"].find({"tender_id": resolved_id}).to_list(100)
    return {
        "status": "compiled",
        "tender_id": resolved_id,
        "rules_count": len(saved_rules),
        "rules": [doc_to_dict(r) for r in saved_rules],
    }
