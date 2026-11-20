from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import RiskCheck
from models import User, Negotiation
from auth import get_current_user, require_roles
import json

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/checks")
def get_risk_checks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(RiskCheck)
    if user.role != "ADMIN":
        query = query.filter(RiskCheck.buyer_user_id == user.id)
    checks = query.order_by(RiskCheck.created_at.desc()).limit(200).all()
    return [
        {
            "id": c.id,
            "transaction_id": c.transaction_id,
            "check_type": c.check_type,
            "result": c.result,
            "details": json.loads(c.details) if c.details else {},
            "created_at": c.created_at.isoformat() if c.created_at else None
        }
        for c in checks
    ]
