from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from models import Transaction, Negotiation, Merchant, User
from auth import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("")
def list_transactions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Transaction)
    if user.role == "CUSTOMER":
        query = query.filter(Transaction.buyer_user_id == user.id)
    elif user.role == "MERCHANT":
        query = query.join(Negotiation, Transaction.negotiation_id == Negotiation.id).join(Merchant, Negotiation.merchant_id == Merchant.id).filter(Merchant.owner_user_id == user.id)
    txs = query.order_by(Transaction.created_at.desc()).limit(100).all()
    return [
        {
            "id": t.id,
            "tx_ref": t.tx_ref,
            "merchant_name": t.merchant_name,
            "product_name": t.product_name,
            "amount_sats": t.amount_sats,
            "payment_method": t.payment_method,
            "status": t.status,
            "mode": t.mode,
            "verification_status": t.verification_status,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in txs
    ]
