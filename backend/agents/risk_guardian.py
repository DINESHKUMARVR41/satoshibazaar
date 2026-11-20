import json
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Negotiation, PaymentInvoice, RiskCheck, InventoryReservation

MAX_TRANSACTION_SATS = int(os.getenv("MAX_TRANSACTION_SATS", "1000000"))


class RiskGuardian:
    """Deterministic risk validation - no LLM involved."""

    def validate_transaction(self, negotiation_id: int, invoice_amount_sats: int, db: Session, require_approval: bool = True):
        checks = []
        warnings = []
        is_valid = True

        def add_check(check_type: str, result: str, details: dict):
            negotiation = db.query(Negotiation).filter(Negotiation.id == negotiation_id).first() if negotiation_id else None
            rc = RiskCheck(
                transaction_id=None,
                buyer_user_id=negotiation.buyer_user_id if negotiation else None,
                check_type=check_type,
                result=result,
                details=json.dumps(details),
                created_at=datetime.now(timezone.utc)
            )
            db.add(rc)
            checks.append({"check_type": check_type, "result": result, "details": details})

        # 1. Amount limit check
        if invoice_amount_sats > MAX_TRANSACTION_SATS:
            is_valid = False
            add_check("amount_limit", "FAIL", {
                "invoice_amount": invoice_amount_sats,
                "max_allowed": MAX_TRANSACTION_SATS,
                "reason": f"Amount {invoice_amount_sats} sats exceeds maximum allowed {MAX_TRANSACTION_SATS} sats"
            })
        else:
            add_check("amount_limit", "PASS", {
                "invoice_amount": invoice_amount_sats,
                "max_allowed": MAX_TRANSACTION_SATS
            })
        if invoice_amount_sats <= 0:
            is_valid = False
            add_check("positive_amount", "FAIL", {"invoice_amount": invoice_amount_sats, "reason": "Amount must be positive"})
        else:
            add_check("positive_amount", "PASS", {"invoice_amount": invoice_amount_sats})

        # 2. Negotiation exists and is accepted
        neg = db.query(Negotiation).filter(Negotiation.id == negotiation_id).first() if negotiation_id else None

        if negotiation_id and not neg:
            is_valid = False
            add_check("negotiation_exists", "FAIL", {"negotiation_id": negotiation_id, "reason": "Negotiation not found"})
        elif neg:
            if neg.status != "accepted":
                is_valid = False
                add_check("negotiation_status", "FAIL", {"status": neg.status, "reason": "Negotiation not in accepted state"})
            else:
                add_check("negotiation_status", "PASS", {"status": neg.status})

            if neg.final_price_sats is not None and invoice_amount_sats > neg.buyer_budget_sats:
                is_valid = False
                add_check("buyer_budget", "FAIL", {
                    "invoice_amount": invoice_amount_sats,
                    "budget_sats": neg.buyer_budget_sats,
                    "reason": "Invoice amount exceeds the buyer's maximum budget"
                })
            else:
                add_check("buyer_budget", "PASS", {"budget_sats": neg.buyer_budget_sats})

            # 3. Invoice amount matches agreed price
            if neg.final_price_sats:
                tolerance = 0.01  # 1%
                min_amount = int(neg.final_price_sats * (1 - tolerance))
                max_amount = int(neg.final_price_sats * (1 + tolerance))
                if not (min_amount <= invoice_amount_sats <= max_amount):
                    is_valid = False
                    add_check("amount_match", "FAIL", {
                        "invoice_amount": invoice_amount_sats,
                        "agreed_price": neg.final_price_sats,
                        "tolerance_pct": 1,
                        "reason": "Invoice amount does not match agreed negotiation price"
                    })
                else:
                    add_check("amount_match", "PASS", {
                        "invoice_amount": invoice_amount_sats,
                        "agreed_price": neg.final_price_sats
                    })

            # 4. Duplicate payment check
            existing_paid = db.query(PaymentInvoice).filter(
                PaymentInvoice.negotiation_id == negotiation_id,
                PaymentInvoice.status.in_(["PAID", "PENDING", "CREATING", "PROVIDER_ERROR"])
            ).first()
            if existing_paid:
                is_valid = False
                add_check("duplicate_payment", "FAIL", {
                    "existing_invoice": existing_paid.invoice_id,
                    "reason": "A paid or pending invoice already exists for this negotiation"
                })
            else:
                add_check("duplicate_payment", "PASS", {"reason": "No duplicate payment found"})

            # 5. Customer approval check
            if require_approval and not neg.approved_by_customer:
                is_valid = False
                add_check("customer_approval", "FAIL", {"reason": "Customer has not approved this transaction"})
                warnings.append("Customer must explicitly approve before payment can proceed")
            elif neg.approved_by_customer:
                add_check("customer_approval", "PASS", {})
            else:
                add_check("customer_approval", "PENDING", {"reason": "Explicit customer approval is required before invoice creation"})

            if require_approval:
                reservation = db.query(InventoryReservation).filter(
                    InventoryReservation.negotiation_id == negotiation_id,
                    InventoryReservation.status == "RESERVED",
                ).first()
                if not reservation:
                    is_valid = False
                    add_check("inventory_reservation", "FAIL", {"reason": "Inventory is not reserved for this order"})
                else:
                    add_check("inventory_reservation", "PASS", {"quantity_reserved": reservation.quantity})

        try:
            db.commit()
        except Exception:
            db.rollback()

        return is_valid, checks, warnings


risk_guardian = RiskGuardian()
