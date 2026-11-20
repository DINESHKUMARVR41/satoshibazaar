from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Negotiation, User
from auth import require_roles
from models import Product, InventoryReservation
from sqlalchemy import update
from datetime import datetime, timedelta, timezone
import math
import json

router = APIRouter(prefix="/api/negotiations", tags=["negotiations"])


@router.get("/{negotiation_id}")
def get_negotiation(negotiation_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    neg = db.query(Negotiation).filter(Negotiation.id == negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not neg:
        raise HTTPException(status_code=404, detail="Negotiation not found")
    return {
        "id": neg.id,
        "session_id": neg.session_id,
        "merchant_id": neg.merchant_id,
        "product_id": neg.product_id,
        "buyer_budget_sats": neg.buyer_budget_sats,
        "initial_offer_sats": neg.initial_offer_sats,
        "final_price_sats": neg.final_price_sats,
        "rounds": json.loads(neg.rounds) if neg.rounds else [],
        "status": neg.status,
        "approved_by_customer": neg.approved_by_customer,
        "created_at": neg.created_at.isoformat() if neg.created_at else None,
        "completed_at": neg.completed_at.isoformat() if neg.completed_at else None
    }


@router.post("/{negotiation_id}/approve")
def approve_negotiation(negotiation_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    neg = db.query(Negotiation).filter(Negotiation.id == negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not neg:
        raise HTTPException(status_code=404, detail="Negotiation not found")
    if neg.status != "accepted" or not neg.final_price_sats or neg.final_price_sats > neg.buyer_budget_sats:
        raise HTTPException(status_code=400, detail="Only an accepted offer within the buyer's budget can be approved.")
    existing_reservation = db.query(InventoryReservation).filter(InventoryReservation.negotiation_id == neg.id).first()
    if existing_reservation and existing_reservation.status == "RESERVED":
        return {"message": "Offer approved and inventory reserved", "negotiation_id": negotiation_id, "approved": True}
    reserve_quantity = max(1, math.ceil(neg.requested_quantity))
    result = db.execute(
        update(Product)
        .where(Product.id == neg.product_id, Product.quantity_available >= reserve_quantity)
        .values(quantity_available=Product.quantity_available - reserve_quantity)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="The requested inventory is no longer available.")
    now = datetime.now(timezone.utc)
    db.add(InventoryReservation(
        negotiation_id=neg.id,
        product_id=neg.product_id,
        quantity=reserve_quantity,
        status="RESERVED",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    ))
    neg.approved_by_customer = True
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not reserve inventory. Please try again.")
    return {"message": "Negotiation approved by customer", "negotiation_id": negotiation_id, "approved": True}


@router.post("/{negotiation_id}/reject")
def reject_negotiation(negotiation_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    neg = db.query(Negotiation).filter(Negotiation.id == negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not neg:
        raise HTTPException(status_code=404, detail="Negotiation not found")
    if neg.approved_by_customer:
        raise HTTPException(status_code=409, detail="An approved offer cannot be rejected after invoice creation.")
    neg.status = "rejected"
    db.commit()
    return {"message": "Offer rejected", "negotiation_id": negotiation_id, "status": neg.status}
