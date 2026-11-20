"""Payment orchestration with immutable per-invoice mode and isolated providers."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import InventoryReservation, Merchant, Negotiation, PaymentInvoice, Product, Transaction
from services.payment_providers import active_payment_mode, build_provider

logger = logging.getLogger(__name__)


class LightningService:
    def __init__(self, mode: str | None = None, provider_factory=build_provider):
        self.mode = mode or active_payment_mode()
        self.provider_factory = provider_factory

    @staticmethod
    def _utc(value):
        if value and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def create_invoice(self, amount_sats: int, memo: str, negotiation_id: int = None, is_demo: bool | None = None, db: Session = None):
        if is_demo is not None and is_demo != (self.mode == "demo"):
            raise RuntimeError("Requested invoice mode does not match server PAYMENT_MODE.")
        if db is None:
            raise RuntimeError("A database session is required to create an invoice.")
        if amount_sats <= 0:
            raise RuntimeError("Invoice amount must be positive.")

        invoice_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        inv = PaymentInvoice(
            invoice_id=invoice_id,
            negotiation_id=negotiation_id,
            merchant_id=None,
            payment_hash=None,
            checking_id=None,
            bolt11="",
            amount_sats=amount_sats,
            is_demo=self.mode == "demo",
            payment_mode=self.mode,
            provider_name={"demo": "demo_simulator", "testnet": "lnbits_testnet", "live": "lnbits_live"}.get(self.mode, self.mode),
            environment=self.mode,
            status="CREATING",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        try:
            provider = self.provider_factory(self.mode)
            result = provider.create_invoice(amount_sats, memo, {"satoshibazaar_invoice_id": invoice_id, "negotiation_id": negotiation_id})
            inv.bolt11 = result.payment_request
            inv.payment_hash = result.payment_hash
            inv.checking_id = result.checking_id
            inv.status = "PENDING"
            negotiation = db.query(Negotiation).filter(Negotiation.id == negotiation_id).first() if negotiation_id else None
            inv.merchant_id = negotiation.merchant_id if negotiation else None
            product = db.query(Product).filter(Product.id == negotiation.product_id).first() if negotiation and negotiation.product_id else None
            merchant = db.query(Merchant).filter(Merchant.id == negotiation.merchant_id).first() if negotiation and negotiation.merchant_id else None
            db.add(Transaction(
                tx_ref=f"{self.mode.upper()}-{uuid.uuid4().hex[:12].upper()}",
                negotiation_id=negotiation.id if negotiation else None,
                merchant_id=negotiation.merchant_id if negotiation else None,
                invoice_id=inv.id,
                buyer_user_id=negotiation.buyer_user_id if negotiation else None,
                merchant_name=merchant.name if merchant else "",
                product_name=product.name if product else "",
                amount_sats=amount_sats,
                payment_method="lightning",
                status="DEMO_INVOICE_CREATED" if self.mode == "demo" else "PAYMENT_PENDING",
                mode=self.mode,
                provider_name={"demo": "demo_simulator", "testnet": "lnbits_testnet", "live": "lnbits_live"}.get(self.mode, self.mode),
                environment=self.mode,
                verification_status="simulated_non_payable" if self.mode == "demo" else f"{self.mode}_awaiting_provider_confirmation",
                created_at=now,
            ))
            db.commit()
            db.refresh(inv)
        except Exception:
            db.rollback()
            intent = db.query(PaymentInvoice).filter(PaymentInvoice.invoice_id == invoice_id).first()
            if intent:
                intent.status = "PROVIDER_ERROR"
                db.commit()
            raise
        return inv

    def simulate_payment(self, invoice_id: str, db: Session):
        inv = db.query(PaymentInvoice).filter(PaymentInvoice.invoice_id == invoice_id, PaymentInvoice.payment_mode == "demo").first()
        if not inv:
            raise RuntimeError("Simulated payments are available only for demo invoices.")
        if inv.status != "PENDING":
            raise RuntimeError(f"Invoice cannot be simulated from status {inv.status}.")
        if inv.expires_at and datetime.now(timezone.utc) > self._utc(inv.expires_at):
            inv.status = "EXPIRED"
            db.commit()
            return inv
        inv.status = "SIMULATED_PAID"
        inv.paid_at = datetime.now(timezone.utc)
        tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).first()
        if tx:
            tx.status = "SIMULATED_COMPLETED"
            tx.verification_status = "simulated_payment_and_settlement"
        reservation = db.query(InventoryReservation).filter(
            InventoryReservation.negotiation_id == inv.negotiation_id,
            InventoryReservation.status == "RESERVED",
        ).first() if inv.negotiation_id else None
        if reservation:
            reservation.status = "FULFILLED"
        db.commit()
        return inv

    def check_payment(self, invoice_id: str, db: Session):
        inv = db.query(PaymentInvoice).filter(PaymentInvoice.invoice_id == invoice_id).first()
        if not inv:
            return None
        if inv.payment_mode == "demo" or inv.status in {"PAID", "SIMULATED_PAID", "PROVIDER_ERROR", "FAILED", "EXPIRED"}:
            if inv.status == "PENDING" and inv.expires_at and datetime.now(timezone.utc) > self._utc(inv.expires_at):
                inv.status = "EXPIRED"
                tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).first()
                if tx and tx.status == "PAYMENT_PENDING":
                    tx.status = "EXPIRED"
                db.commit()
            return inv
        if inv.expires_at and datetime.now(timezone.utc) > self._utc(inv.expires_at):
            inv.status = "EXPIRED"
            tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).first()
            if tx and tx.status == "PAYMENT_PENDING":
                tx.status = "EXPIRED"
            db.commit()
            return inv
        if not inv.checking_id:
            return inv
        try:
            result = self.provider_factory(inv.payment_mode).check_payment(inv.checking_id, inv.amount_sats)
            if result.status == "PAID":
                inv.status = "PAID"
                inv.paid_at = datetime.now(timezone.utc)
                tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).first()
                if tx:
                    tx.status = "PAYMENT_CONFIRMED"
                    tx.verification_status = f"{inv.payment_mode}_buyer_payment_verified_settlement_pending"
            elif result.status == "FAILED":
                inv.status = "FAILED"
                tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).first()
                if tx and tx.status == "PAYMENT_PENDING":
                    tx.status = "FAILED"
            db.commit()
        except Exception as exc:
            logger.warning("Payment status check failed for mode=%s (%s)", inv.payment_mode, type(exc).__name__)
        return inv


lightning_service = LightningService()
