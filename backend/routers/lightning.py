from datetime import datetime, timezone
import base64
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import update
from starlette.concurrency import run_in_threadpool

from auth import require_roles
from database import get_db
from models import PaymentInvoice, Negotiation, Transaction, User
from schemas import AlbyWalletConnectRequest, InvoiceCreateRequest, PaymentApprovalRequest
from services.lightning_service import lightning_service
from services.payment_providers import active_payment_mode, build_provider
from agents.risk_guardian import risk_guardian

router = APIRouter(prefix="/api/lightning", tags=["lightning"])


def _network(mode):
    return {"demo": "simulated", "testnet": "testnet", "live": "mainnet", "alby_sandbox": "sandbox"}.get(mode, "unknown")


def _invoice_qr(invoice):
    if invoice.is_demo or not invoice.bolt11:
        return None
    import qrcode
    image = qrcode.make(invoice.bolt11)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _invoice_out(inv):
    return {
        "invoice_id": inv.invoice_id, "payment_hash": inv.payment_hash,
        "bolt11": inv.bolt11, "amount_sats": inv.amount_sats,
        "amount_msat": inv.amount_msat or inv.amount_sats * 1000,
        "is_demo": inv.payment_mode == "demo", "payment_mode": inv.payment_mode,
        "network": _network(inv.payment_mode), "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
        "merchant_verification": "verified" if inv.verified_at else "pending",
        "payment_attempted": bool(inv.payment_attempted_at),
        "mode": inv.payment_mode.upper(), "qr_code_data": _invoice_qr(inv),
    }


def _owned_invoice(invoice_id, db, user):
    inv = db.query(PaymentInvoice).filter(PaymentInvoice.invoice_id == invoice_id).first()
    if not inv or not inv.negotiation_id:
        return None
    negotiation = db.query(Negotiation).filter(
        Negotiation.id == inv.negotiation_id, Negotiation.buyer_user_id == user.id,
    ).first()
    return inv if negotiation else None


@router.post("/connect")
async def connect_alby_wallets(http_request: Request, payload: AlbyWalletConnectRequest, user: User = Depends(require_roles("CUSTOMER"))):
    """Configure faucet URLs from the local UI without persisting or echoing secrets."""
    import os
    from services.alby_sandbox import AlbySandboxError, AlbySandboxPaymentProvider, _valid_faucet_uri, set_runtime_wallet_uris

    if (os.getenv("APP_ENV", "development").lower() != "development"
            or not http_request.client
            or http_request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}):
        raise HTTPException(403, "In-app wallet setup is only enabled for local development.")
    buyer_uri, merchant_uri = payload.buyer_url.strip(), payload.merchant_url.strip()
    if (len(buyer_uri) > 2048 or len(merchant_uri) > 2048
            or not _valid_faucet_uri(buyer_uri) or not _valid_faucet_uri(merchant_uri)
            or buyer_uri == merchant_uri
            or buyer_uri.split("?", 1)[0] == merchant_uri.split("?", 1)[0]):
        raise HTTPException(400, "Enter two distinct, valid NWC Faucet wallet connection URLs.")

    set_runtime_wallet_uris(buyer_uri, merchant_uri)
    provider = AlbySandboxPaymentProvider()
    try:
        return await provider.status()
    except AlbySandboxError as exc:
        # The credentials are installed in this process; transient relay failures
        # should not discard them or return the submitted connection strings.
        return {
            "connected": False,
            "configured": provider.configured,
            "mode": provider.mode,
            "network": provider.network,
            "connection_error": str(exc),
        }


@router.get("/status")
async def lightning_status(user: User = Depends(require_roles("CUSTOMER"))):
    mode = active_payment_mode()
    provider = build_provider(mode)
    if mode == "alby_sandbox":
        try:
            return await provider.status()
        except Exception as exc:
            from services.alby_sandbox import AlbySandboxError
            if isinstance(exc, AlbySandboxError):
                raise HTTPException(503, {"code": exc.code, "message": str(exc)}) from exc
            raise HTTPException(503, "Alby sandbox wallet connection failed.") from exc
    return {"connected": bool(provider.configured), "mode": mode, "network": _network(mode), "label": mode.upper()}


@router.get("/balance")
async def lightning_balance(wallet: str = "buyer", user: User = Depends(require_roles("CUSTOMER"))):
    mode = active_payment_mode()
    provider = build_provider(mode)
    if mode == "alby_sandbox":
        try:
            status = await provider.status()
            result = await provider.balance(wallet)
            result["wallet_alias"] = status[f"{wallet}_wallet"]["alias"]
            return result
        except Exception as exc:
            from services.alby_sandbox import AlbySandboxError
            if isinstance(exc, AlbySandboxError):
                raise HTTPException(503, {"code": exc.code, "message": str(exc)}) from exc
            raise HTTPException(503, "Alby sandbox balance is unavailable.") from exc
    raise HTTPException(409, "Wallet balances are available only in Alby sandbox mode.")


@router.get("/transactions")
async def lightning_transactions(wallet: str = "buyer", user: User = Depends(require_roles("CUSTOMER"))):
    mode = active_payment_mode()
    if mode != "alby_sandbox":
        return []
    provider = build_provider(mode)
    try:
        status = await provider.status()
        rows = await provider.transactions(wallet=wallet)
        for row in rows:
            row["wallet_alias"] = status[f"{wallet}_wallet"]["alias"]
        return rows
    except Exception as exc:
        from services.alby_sandbox import AlbySandboxError
        if isinstance(exc, AlbySandboxError):
            raise HTTPException(503, {"code": exc.code, "message": str(exc)}) from exc
        raise HTTPException(503, "Alby sandbox transaction history is unavailable.") from exc


@router.post("/invoices")
async def create_invoice(request: InvoiceCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    if not request.negotiation_id:
        raise HTTPException(400, "An approved negotiation is required to create an invoice.")
    negotiation = db.query(Negotiation).filter(Negotiation.id == request.negotiation_id, Negotiation.buyer_user_id == user.id).first()
    if not negotiation:
        raise HTTPException(404, "Negotiation not found")
    mode = active_payment_mode()
    provider = build_provider(mode)
    if not provider.configured:
        detail = "Configure two distinct Alby faucet NWC wallet URLs." if mode == "alby_sandbox" else f"{mode} payment provider is not configured; no fallback is allowed."
        raise HTTPException(503, detail)
    prior = db.query(PaymentInvoice).filter(PaymentInvoice.negotiation_id == negotiation.id).order_by(PaymentInvoice.id.desc()).first()
    if prior and prior.status != "PROVIDER_ERROR":
        if prior.payment_mode != mode:
            raise HTTPException(409, "This approved negotiation already has an invoice in a different payment mode.")
        if prior.amount_sats != request.amount_sats:
            raise HTTPException(409, "The approved negotiation already has an invoice for a different amount.")
        if prior.bolt11:
            return _invoice_out(prior)
        raise HTTPException(409, "An invoice is already being created for this negotiation.")
    valid, checks, warnings = risk_guardian.validate_transaction(request.negotiation_id, request.amount_sats, db)
    if not valid:
        raise HTTPException(400, {"error": "Risk validation failed", "checks": checks, "warnings": warnings})
    try:
        if mode == "alby_sandbox":
            inv = await lightning_service.create_invoice_async(
                request.amount_sats, request.description or f"SatoshiBazaar order · {request.amount_sats} sats",
                request.negotiation_id, db,
            )
        else:
            inv = await run_in_threadpool(
                lightning_service.create_invoice, request.amount_sats,
                request.description or f"SatoshiBazaar payment - {request.amount_sats} sats",
                request.negotiation_id, None, db,
            )
    except Exception as exc:
        from services.alby_sandbox import AlbySandboxError
        if isinstance(exc, AlbySandboxError):
            raise HTTPException(502, {"code": exc.code, "message": str(exc)}) from exc
        raise HTTPException(502, "Lightning provider could not create an invoice.") from exc
    return _invoice_out(inv)


@router.get("/invoices/{invoice_id}")
async def check_invoice(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    inv = _owned_invoice(invoice_id, db, user)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.payment_mode == "alby_sandbox":
        inv = await lightning_service.check_payment_async(invoice_id, db)
    else:
        inv = await run_in_threadpool(lightning_service.check_payment, invoice_id, db)
    return _invoice_out(inv)


@router.post("/invoices/{invoice_id}/pay")
async def pay_invoice(invoice_id: str, approval: PaymentApprovalRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    if not approval.approve:
        raise HTTPException(400, "Buyer approval is required before paying this invoice.")
    inv = _owned_invoice(invoice_id, db, user)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if active_payment_mode() != "alby_sandbox" or inv.payment_mode != "alby_sandbox":
        raise HTTPException(409, "NWC buyer payment is available only for Alby sandbox invoices.")
    inv = await lightning_service.check_payment_async(invoice_id, db)
    if inv.status == "PAID":
        return _invoice_out(inv)
    if inv.status != "PENDING":
        raise HTTPException(409, f"Invoice cannot be paid from status {inv.status}.")
    if inv.payment_attempted_at:
        raise HTTPException(409, "A payment was already attempted. Refresh merchant verification; do not pay again.")
    now = datetime.now(timezone.utc)
    result = db.execute(update(PaymentInvoice).where(
        PaymentInvoice.id == inv.id, PaymentInvoice.status == "PENDING",
        PaymentInvoice.payment_attempted_at.is_(None),
    ).values(status="PAYING", payment_attempted_at=now))
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(409, "A payment attempt is already in progress; refresh invoice status.")
    db.refresh(inv)
    provider = build_provider("alby_sandbox")
    try:
        await provider.pay_invoice(inv.bolt11, inv.payment_hash, inv.amount_sats)
        inv.status = "PENDING"
        db.commit()
        inv = await lightning_service.check_payment_async(invoice_id, db)
    except Exception as exc:
        from services.alby_sandbox import AlbySandboxError
        if isinstance(exc, AlbySandboxError) and exc.ambiguous:
            inv.status = "PAYMENT_UNKNOWN"
            db.commit()
            raise HTTPException(503, {"code": exc.code, "message": str(exc), "retry_allowed": False}) from exc
        inv.status = "FAILED"
        tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).first()
        if tx:
            tx.status = "FAILED"
            tx.verification_status = "alby_sandbox_payment_failed"
        db.commit()
        if isinstance(exc, AlbySandboxError):
            raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
        raise HTTPException(502, "Alby sandbox payment failed.") from exc
    return _invoice_out(inv)


@router.post("/invoices/{invoice_id}/simulate-payment")
async def simulate_payment(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    inv = _owned_invoice(invoice_id, db, user)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if active_payment_mode() != "demo" or inv.payment_mode != "demo":
        raise HTTPException(409, "Simulated payments are only available in DEMO mode.")
    try:
        inv = await run_in_threadpool(lightning_service.simulate_payment, invoice_id, db)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"invoice_id": inv.invoice_id, "payment_mode": inv.payment_mode, "status": inv.status, "simulated": True}
