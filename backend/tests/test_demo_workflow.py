import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import Base  # noqa: E402
from seed import run_seed  # noqa: E402
from agents.buyer_agent import buyer_agent  # noqa: E402
from agents import run_full_pipeline  # noqa: E402
from agents.risk_guardian import risk_guardian  # noqa: E402
from models import Negotiation, PaymentInvoice, Transaction  # noqa: E402
from services.lightning_service import LightningService  # noqa: E402
from services import payment_providers  # noqa: E402


def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_buyer_extracts_quantity_unit_budget_and_product(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = buyer_agent.parse_request(
        "I need 10 kg of rice in Dakar for a maximum total of 250,000 sats.",
        "Dakar, Senegal",
    )
    assert result["product"] == "rice"
    assert result["quantity_value"] == 10
    assert result["unit"] == "kg"
    assert result["budget_sats"] == 250000


def test_seeded_end_to_end_rice_scenario(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    db = fresh_db()
    run_seed(db)
    result = run_full_pipeline(
        "I need 10 kg of rice in Dakar for a maximum total of 250,000 sats.",
        "Dakar, Senegal",
        db,
    )
    assert result["buyer_result"]["quantity_value"] == 10
    assert result["negotiation"]["agreed_price_sats"] == 240000
    assert result["negotiation"]["within_budget"] is True
    assert result["negotiation"]["best_merchant"]["merchant_name"] == "BioFarm Direct"
    assert result["risk_assessment"]["is_valid"] is True
    assert len(result["messages"]) >= 5


def test_risk_guardian_requires_approval_for_invoice():
    db = fresh_db()
    negotiation = Negotiation(
        session_id="test-session", merchant_id=None, product_id=None,
        buyer_budget_sats=250000, initial_offer_sats=240000,
        final_price_sats=240000, status="accepted", approved_by_customer=False,
    )
    db.add(negotiation)
    db.commit()
    allowed, checks, _ = risk_guardian.validate_transaction(negotiation.id, 240000, db)
    assert not allowed
    assert any(c["check_type"] == "customer_approval" and c["result"] == "FAIL" for c in checks)


def test_demo_invoice_is_labeled_and_duplicate_simulation_is_rejected():
    db = fresh_db()
    service = LightningService(mode="demo")
    invoice = service.create_invoice(240000, "demo", db=db)
    assert invoice.payment_mode == "demo"
    assert invoice.bolt11.startswith("DEMO-SIMULATED-NOT-PAYABLE-")
    assert service.check_payment(invoice.invoice_id, db).status == "PENDING"
    assert service.simulate_payment(invoice.invoice_id, db).status == "SIMULATED_PAID"
    try:
        service.simulate_payment(invoice.invoice_id, db)
    except RuntimeError as exc:
        assert "cannot be simulated" in str(exc)
    else:
        raise AssertionError("A simulated payment must not be applied twice")


def test_expired_demo_invoice_cannot_be_simulated():
    from datetime import datetime, timedelta, timezone

    db = fresh_db()
    service = LightningService(mode="demo")
    invoice = service.create_invoice(1000, "demo", db=db)
    invoice.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert service.simulate_payment(invoice.invoice_id, db).status == "EXPIRED"


def test_expired_testnet_invoice_is_never_reported_paid(monkeypatch):
    from datetime import datetime, timedelta, timezone

    _configure_testnet(monkeypatch)
    db = fresh_db()
    provider = type("Provider", (), {
        "create_invoice": lambda self, amount, memo, extra: payment_providers.ProviderInvoice(
            "lntb10u1" + "a" * 100, "hash", "check", "testnet",
        ),
    })()
    service = LightningService(mode="testnet", provider_factory=lambda mode: provider)
    invoice = service.create_invoice(1000, "testnet", db=db)
    invoice.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    class MustNotCheckProvider:
        def check_payment(self, *_args):
            raise AssertionError("Expired invoice must not be checked as payable")

    service.provider_factory = lambda mode: MustNotCheckProvider()
    assert service.check_payment(invoice.invoice_id, db).status == "EXPIRED"


def test_live_mode_never_falls_back_to_demo_without_its_credentials(monkeypatch):
    monkeypatch.setenv("PAYMENT_MODE", "live")
    monkeypatch.delenv("LNBITS_LIVE_URL", raising=False)
    monkeypatch.delenv("LNBITS_LIVE_INVOICE_KEY", raising=False)
    monkeypatch.delenv("LNBITS_LIVE_ADMIN_KEY", raising=False)
    service = LightningService(mode="live")
    try:
        service.create_invoice(1000, "live", db=fresh_db())
    except RuntimeError as exc:
        assert "requires its own LNbits" in str(exc)
    else:
        raise AssertionError("Live mode must not return a demo invoice")


def _configure_testnet(monkeypatch):
    monkeypatch.setenv("LNBITS_TESTNET_URL", "https://testnet-lnbits.example")
    monkeypatch.setenv("LNBITS_TESTNET_INVOICE_KEY", "testnet-invoice-test-key")
    monkeypatch.setenv("LNBITS_TESTNET_ADMIN_KEY", "testnet-admin-test-key")


def test_testnet_invoice_rejects_wrong_network_and_amount(monkeypatch):
    from unittest.mock import MagicMock

    _configure_testnet(monkeypatch)
    monkeypatch.setattr(payment_providers.httpx, "Client", MagicMock())
    client = payment_providers.httpx.Client.return_value.__enter__.return_value
    client.post.return_value.json.return_value = {
        "payment_request": "lnbc10u1" + "a" * 100,
        "payment_hash": "hash",
        "checking_id": "check",
    }
    client.post.return_value.raise_for_status.return_value = None
    try:
        payment_providers.TestnetPaymentProvider().create_invoice(1000, "test", {})
    except RuntimeError as exc:
        assert "requires testnet" in str(exc)
    else:
        raise AssertionError("Wrong-network invoice must be rejected")

    client.post.return_value.json.return_value["payment_request"] = "lntb11u1" + "a" * 100
    try:
        payment_providers.TestnetPaymentProvider().create_invoice(1000, "test", {})
    except RuntimeError as exc:
        assert "wrong amount" in str(exc)
    else:
        raise AssertionError("Wrong-amount invoice must be rejected")


def test_testnet_payment_requires_independent_exact_provider_verification(monkeypatch):
    from unittest.mock import MagicMock

    _configure_testnet(monkeypatch)
    monkeypatch.setattr(payment_providers.httpx, "Client", MagicMock())
    client = payment_providers.httpx.Client.return_value.__enter__.return_value
    client.post.return_value.json.return_value = {
        "payment_request": "lntb10u1" + "a" * 100,
        "payment_hash": "hash-1",
        "checking_id": "check-1",
    }
    client.post.return_value.raise_for_status.return_value = None
    client.get.return_value.raise_for_status.return_value = None
    db = fresh_db()
    service = LightningService(mode="testnet")
    invoice = service.create_invoice(1000, "testnet", db=db)
    client.get.return_value.json.return_value = {
        "paid": True, "details": {"checking_id": "check-1", "amount": 999, "status": "success"},
    }
    assert service.check_payment(invoice.invoice_id, db).status == "FAILED"
    client.post.return_value.json.return_value["checking_id"] = "check-2"
    client.post.return_value.json.return_value["payment_hash"] = "hash-2"
    verified_invoice = service.create_invoice(1000, "testnet", db=db)
    client.get.return_value.json.return_value["details"]["amount"] = 1000
    client.get.return_value.json.return_value["details"]["checking_id"] = "check-2"
    assert service.check_payment(verified_invoice.invoice_id, db).status == "PAID"
    assert service.check_payment(verified_invoice.invoice_id, db).status == "PAID"
    tx = db.query(Transaction).filter(Transaction.invoice_id == verified_invoice.id).one()
    assert db.query(Transaction).filter(Transaction.invoice_id == verified_invoice.id).count() == 1
    assert tx.status == "PAYMENT_CONFIRMED"
    assert tx.verification_status.startswith("testnet_")


def test_testnet_merchant_payout_uses_admin_key_then_invoice_key_for_verification(monkeypatch):
    from unittest.mock import MagicMock

    _configure_testnet(monkeypatch)
    monkeypatch.setattr(payment_providers.httpx, "Client", MagicMock())
    client = payment_providers.httpx.Client.return_value.__enter__.return_value
    client.post.return_value.raise_for_status.return_value = None
    client.post.return_value.json.return_value = {"checking_id": "out-check", "payment_hash": "out-hash"}
    client.get.return_value.raise_for_status.return_value = None
    client.get.return_value.json.return_value = {
        "paid": True,
        "details": {"checking_id": "out-check", "amount": -1000, "status": "success", "payment_hash": "out-hash"},
    }
    provider = payment_providers.TestnetPaymentProvider()
    sent = provider.pay_invoice("lntb10u1" + "a" * 100, 1000)
    assert sent.status == "PENDING"
    assert client.post.call_args.kwargs["headers"]["X-Api-Key"] == "testnet-admin-test-key"
    verified = provider.check_payment(sent.checking_id, 1000)
    assert verified.status == "PAID"
    assert verified.payment_hash == "out-hash"
    assert client.get.call_args.kwargs["headers"]["X-Api-Key"] == "testnet-invoice-test-key"


def test_mode_credentials_are_separate_and_url_must_not_be_shared(monkeypatch):
    from services.payment_providers import build_provider

    _configure_testnet(monkeypatch)
    monkeypatch.setenv("LNBITS_LIVE_URL", "https://live-lnbits.example")
    monkeypatch.setenv("LNBITS_LIVE_INVOICE_KEY", "live-invoice-key")
    monkeypatch.setenv("LNBITS_LIVE_ADMIN_KEY", "live-admin-key")
    assert build_provider("testnet").network == "testnet"
    assert build_provider("live").network == "mainnet"
    monkeypatch.setenv("LNBITS_LIVE_URL", "https://testnet-lnbits.example")
    try:
        build_provider("live")
    except RuntimeError as exc:
        assert "URLs must be distinct" in str(exc)
    else:
        raise AssertionError("Testnet and live URLs must not be shared")


def test_failed_merchant_settlement_never_completes_transaction(monkeypatch):
    from models import PaymentSettlement
    from routers import settlements
    from types import SimpleNamespace

    db = fresh_db()
    transaction = Transaction(
        tx_ref="TESTNET-FAILED-SETTLEMENT", amount_sats=1000, mode="testnet",
        status="SETTLEMENT_PENDING", verification_status="awaiting", payment_method="lightning",
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    record = PaymentSettlement(
        transaction_id=transaction.id, payment_mode="testnet", network="testnet",
        amount_sats=1000, merchant_invoice="lntb10u1" + "a" * 100,
        checking_id="outgoing-check", payment_hash="outgoing-hash", status="PENDING",
    )
    db.add(record)
    db.commit()

    class FailedProvider:
        def check_payment(self, checking_id, expected_sats):
            assert checking_id == "outgoing-check"
            assert expected_sats == 1000
            return SimpleNamespace(status="FAILED", payment_hash="outgoing-hash")

    monkeypatch.setattr(settlements, "build_provider", lambda mode: FailedProvider())
    settlements._verify_settlement(record, transaction, db)
    db.refresh(transaction)
    assert record.status == "FAILED"
    assert transaction.status == "SETTLEMENT_FAILED"
    assert transaction.status != "COMPLETED"
