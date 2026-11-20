from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, require_roles
from database import get_db
from models import InventoryReservation, Merchant, PaymentSettlement, Negotiation, PaymentInvoice, Transaction, User
from schemas import MerchantSettlementRequest
from services.payment_providers import build_provider, bolt11_amount_sats, bolt11_network

router = APIRouter(prefix="/api/transactions", tags=["settlements"])


def _owned_transaction(transaction_id: int, db: Session, user: User):
    return db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.buyer_user_id == user.id,
    ).first()


def _merchant_transaction(transaction_id: int, db: Session, user: User):
    return (
        db.query(Transaction)
        .join(Negotiation, Transaction.negotiation_id == Negotiation.id)
        .join(Merchant, Negotiation.merchant_id == Merchant.id)
        .filter(Transaction.id == transaction_id, Merchant.owner_user_id == user.id)
        .first()
    )


def _out(outcome: PaymentSettlement):
    return {
        "settlement_id": outcome.id,
        "transaction_id": outcome.transaction_id,
        "payment_mode": outcome.payment_mode,
        "network": outcome.network,
        "amount_sats": outcome.amount_sats,
        "status": outcome.status,
        "created_at": outcome.created_at.isoformat() if outcome.created_at else None,
        "verified_at": outcome.verified_at.isoformat() if outcome.verified_at else None,
    }


def _verify_settlement(record: PaymentSettlement, transaction: Transaction, db: Session):
    if record.payment_mode == "demo" or record.status in {"CONFIRMED", "FAILED", "UNKNOWN"}:
        return record
    if record.status != "PENDING" or not record.checking_id:
        return record
    try:
        result = build_provider(record.payment_mode).check_payment(record.checking_id, record.amount_sats)
        if result.status == "PAID":
            if result.payment_hash and record.payment_hash and result.payment_hash != record.payment_hash:
                record.status = "FAILED"
                transaction.status = "SETTLEMENT_FAILED"
            else:
                record.status = "CONFIRMED"
                record.verified_at = datetime.now(timezone.utc)
                transaction.status = "COMPLETED"
                transaction.verification_status = f"{record.payment_mode}_buyer_and_merchant_payments_verified"
                reservation = db.query(InventoryReservation).filter(
                    InventoryReservation.negotiation_id == transaction.negotiation_id,
                    InventoryReservation.status == "RESERVED",
                ).first() if transaction.negotiation_id else None
                if reservation:
                    reservation.status = "FULFILLED"
        elif result.status == "FAILED":
            record.status = "FAILED"
            transaction.status = "SETTLEMENT_FAILED"
            transaction.verification_status = f"{record.payment_mode}_merchant_settlement_failed"
        db.commit()
    except Exception:
        db.rollback()
    return record


@router.post("/{transaction_id}/settlement")
def submit_settlement(
    transaction_id: int,
    payload: MerchantSettlementRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("MERCHANT")),
):
    transaction = _merchant_transaction(transaction_id, db, user)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    existing = db.query(PaymentSettlement).filter(PaymentSettlement.transaction_id == transaction.id).first()
    if existing:
        return _out(_verify_settlement(existing, transaction, db))
    if transaction.status != "PAYMENT_CONFIRMED":
        raise HTTPException(status_code=409, detail="Buyer payment must be provider-verified before merchant settlement.")
    invoice = db.query(PaymentInvoice).filter(PaymentInvoice.id == transaction.invoice_id).first()
    if not invoice or invoice.status != "PAID" or invoice.payment_mode != transaction.mode:
        raise HTTPException(status_code=409, detail="Verified buyer invoice and transaction payment mode do not match.")
    try:
        network = bolt11_network(payload.bolt11)
        amount = bolt11_amount_sats(payload.bolt11)
        if network != {"testnet": "testnet", "live": "mainnet"}.get(transaction.mode):
            raise ValueError(f"Merchant invoice is {network}; transaction requires the {transaction.mode} network.")
        if amount != transaction.amount_sats:
            raise ValueError("Merchant invoice amount must exactly match the agreed transaction amount.")
        provider = build_provider(transaction.mode)
        if transaction.mode == "demo":
            raise ValueError("Demo transactions use simulated settlement and do not accept BOLT11 invoices.")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = PaymentSettlement(
        transaction_id=transaction.id,
        payment_mode=transaction.mode,
        network=network,
        amount_sats=amount,
        merchant_invoice=payload.bolt11,
        status="SUBMITTING",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        sent = provider.pay_invoice(payload.bolt11, transaction.amount_sats)
        record.checking_id = sent.checking_id
        record.payment_hash = sent.payment_hash
        record.status = "PENDING"
        transaction.status = "SETTLEMENT_PENDING"
        transaction.verification_status = f"{transaction.mode}_merchant_payment_submitted_awaiting_verification"
        db.commit()
    except httpx.TransportError as exc:
        # The remote provider may have sent the payment. Never retry an ambiguous send automatically.
        record.status = "UNKNOWN"
        transaction.status = "SETTLEMENT_REVIEW_REQUIRED"
        db.commit()
        raise HTTPException(status_code=503, detail="Settlement result is unknown; do not retry automatically. Reconcile it with LNbits.") from exc
    except Exception as exc:
        record.status = "FAILED"
        transaction.status = "SETTLEMENT_FAILED"
        db.commit()
        raise HTTPException(status_code=502, detail="LNbits did not accept the merchant settlement.") from exc
    return _out(_verify_settlement(record, transaction, db))


@router.get("/{transaction_id}/settlement")
def get_settlement(transaction_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    transaction = _owned_transaction(transaction_id, db, user) or _merchant_transaction(transaction_id, db, user)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    record = db.query(PaymentSettlement).filter(PaymentSettlement.transaction_id == transaction.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Merchant settlement not found")
    return _out(_verify_settlement(record, transaction, db))
