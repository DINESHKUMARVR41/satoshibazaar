from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from schemas import InvoiceCreateRequest, InvoiceOut
from services.lightning_service import lightning_service
from agents.risk_guardian import risk_guardian
from models import PaymentInvoice, Negotiation, User
from auth import require_roles
import base64
import io
from services.payment_providers import active_payment_mode, build_provider


def _invoice_qr(invoice):
    if invoice.is_demo or not invoice.bolt11:
        return None
    import qrcode
    image = qrcode.make(invoice.bolt11)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

router = APIRouter(prefix="/api/lightning", tags=["lightning"])


@router.post("/invoices")
def create_invoice(request: InvoiceCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    if not request.negotiation_id:
        raise HTTPException(status_code=400, detail="An approved negotiation is required to create an invoice.")
    negotiation = db.query(Negotiation).filter(Negotiation.id == request.negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not negotiation:
        raise HTTPException(status_code=404, detail="Negotiation not found")
    mode = active_payment_mode()
    provider = build_provider(mode)
    if mode != "demo" and not provider.configured:
        raise HTTPException(status_code=503, detail=f"{mode} mode is not configured. Add its dedicated LNbits URL, invoice key, and Admin key; no fallback is allowed.")
    is_valid, checks, warnings = risk_guardian.validate_transaction(
        request.negotiation_id, request.amount_sats, db
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail={
            "error": "Risk validation failed",
            "checks": checks,
            "warnings": warnings
        })

    try:
        inv = lightning_service.create_invoice(
            amount_sats=request.amount_sats,
            memo=request.description or f"SatoshiBazaar payment - {request.amount_sats} sats",
            negotiation_id=request.negotiation_id,
            is_demo=None,
            db=db
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Lightning provider could not create an invoice.") from exc
    return {
        "invoice_id": inv.invoice_id,
        "payment_hash": inv.payment_hash,
        "bolt11": inv.bolt11,
        "amount_sats": inv.amount_sats,
        "is_demo": inv.payment_mode == "demo",
        "payment_mode": inv.payment_mode,
        "network": "simulated" if inv.payment_mode == "demo" else "testnet" if inv.payment_mode == "testnet" else "mainnet",
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "mode": inv.payment_mode.upper(),
        "qr_code_data": _invoice_qr(inv),
    }


@router.get("/invoices/{invoice_id}")
def check_invoice(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    inv = db.query(PaymentInvoice).filter(PaymentInvoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    negotiation = db.query(Negotiation).filter(Negotiation.id == inv.negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not negotiation:
        raise HTTPException(status_code=404, detail="Invoice not found")
    inv = lightning_service.check_payment(invoice_id, db)
    return {
        "invoice_id": inv.invoice_id,
        "payment_hash": inv.payment_hash,
        "bolt11": inv.bolt11,
        "amount_sats": inv.amount_sats,
        "is_demo": inv.payment_mode == "demo",
        "payment_mode": inv.payment_mode,
        "network": "simulated" if inv.payment_mode == "demo" else "testnet" if inv.payment_mode == "testnet" else "mainnet",
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
        "mode": inv.payment_mode.upper(),
        "qr_code_data": _invoice_qr(inv),
    }


@router.post("/invoices/{invoice_id}/simulate-payment")
def simulate_payment(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    inv = db.query(PaymentInvoice).filter(PaymentInvoice.invoice_id == invoice_id).first()
    if not inv or inv.negotiation_id is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    negotiation = db.query(Negotiation).filter(Negotiation.id == inv.negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not negotiation:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if active_payment_mode() != "demo" or inv.payment_mode != "demo":
        raise HTTPException(status_code=409, detail="Simulated payments are only available in DEMO mode.")
    try:
        inv = lightning_service.simulate_payment(invoice_id, db)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"invoice_id": inv.invoice_id, "payment_mode": inv.payment_mode, "status": inv.status, "simulated": True}
