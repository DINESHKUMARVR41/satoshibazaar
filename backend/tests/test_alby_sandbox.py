import asyncio
from datetime import datetime, timezone
import sys
from pathlib import Path

import pytest
from coincurve import PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.alby_sandbox import AlbySandboxError, AlbySandboxPaymentProvider, _valid_faucet_uri


BUYER_SECRET = "1" * 64
MERCHANT_SECRET = "2" * 64
BUYER_PUBKEY = PrivateKey(bytes.fromhex(BUYER_SECRET)).public_key.format(compressed=False)[1:33].hex()
MERCHANT_PUBKEY = PrivateKey(bytes.fromhex(MERCHANT_SECRET)).public_key.format(compressed=False)[1:33].hex()
BUYER = f"nostr+walletconnect://{BUYER_PUBKEY}?relay=wss://relay.getalby.com&relay=wss://relay2.getalby.com&secret={BUYER_SECRET}&lud16=nwc111@getalby.com"
MERCHANT = f"nostr+walletconnect://{MERCHANT_PUBKEY}?relay=wss://relay.getalby.com&relay=wss://relay2.getalby.com&secret={MERCHANT_SECRET}&lud16=nwc222@getalby.com"
METHODS = ["get_info", "get_balance", "make_invoice", "pay_invoice", "lookup_invoice", "list_transactions"]
PAYMENT_HASH = "a" * 64


class Wallet:
    def __init__(self, alias):
        self.alias = alias
        self.balance = 12_345
        self.invoice_result = {"invoice": "lnbc10n1" + "q" * 80, "payment_hash": PAYMENT_HASH, "amount": 10_000, "created_at": 1_800_000_000, "expires_at": 1_800_003_600}
        self.lookup_result = {"invoice": self.invoice_result["invoice"], "payment_hash": PAYMENT_HASH, "amount": 10_000, "type": "incoming"}
        self.pay_error = None
        self.pay_calls = 0

    async def get_info(self):
        return {"alias": "NWC", "network": "mainnet", "methods": METHODS}

    async def get_balance(self):
        return self.balance

    async def make_invoice(self, amount_msat, **kwargs):
        self.amount_msat, self.invoice_kwargs = amount_msat, kwargs
        return self.invoice_result

    async def pay_invoice(self, invoice, **kwargs):
        self.pay_calls += 1
        if self.pay_error:
            raise self.pay_error
        return {"preimage": "buyer-preimage"}

    async def lookup_invoice(self, **kwargs):
        self.lookup_args = kwargs
        return self.lookup_result

    async def list_transactions(self, **kwargs):
        self.transaction_kwargs = kwargs
        return [{"amount": -2500, "type": "outgoing", "payment_hash": "hash-2", "created_at": 1_800_000_000}]


def configured(monkeypatch, buyer=None, merchant=None):
    monkeypatch.setenv("ALBY_NWC_BUYER_URL", buyer or BUYER)
    monkeypatch.setenv("ALBY_NWC_MERCHANT_URL", merchant or MERCHANT)
    wallets = {BUYER: Wallet("nwc111"), MERCHANT: Wallet("nwc222")}
    factory = lambda uri, **kwargs: wallets[uri]
    return AlbySandboxPaymentProvider(factory), wallets


@pytest.mark.asyncio
async def test_faucet_uri_is_accepted_by_provider_and_actual_aionwc_parser(monkeypatch):
    provider, _ = configured(monkeypatch)
    assert provider.configured
    from aionwc import NWCClient
    # Construction parses the real faucet-issued NWC URI without contacting its relay.
    buyer = NWCClient(BUYER)
    assert buyer is not None
    assert provider._client("buyer") is not None
    legacy = f"nostr+walletconnect://{BUYER_PUBKEY}?relay=wss%3A%2F%2Frelay.getalby.com%2Fv1&secret={BUYER_SECRET}&lud16=nwc111@getalby.com"
    assert _valid_faucet_uri(legacy)


@pytest.mark.asyncio
async def test_missing_credentials_and_buyer_merchant_separation(monkeypatch):
    monkeypatch.delenv("ALBY_NWC_BUYER_URL", raising=False)
    monkeypatch.delenv("ALBY_NWC_MERCHANT_URL", raising=False)
    with pytest.raises(AlbySandboxError, match="both buyer and merchant"):
        await AlbySandboxPaymentProvider().status()
    provider, _ = configured(monkeypatch, merchant=BUYER)
    assert not provider.configured
    with pytest.raises(AlbySandboxError, match="distinct Alby faucet"):
        await provider.status()


def test_alby_provider_is_independent_of_lnbits_configuration(monkeypatch):
    from services.payment_providers import build_provider
    monkeypatch.setenv("LNBITS_TESTNET_URL", "https://same.example")
    monkeypatch.setenv("LNBITS_LIVE_URL", "https://same.example")
    monkeypatch.setenv("LNBITS_TESTNET_INVOICE_KEY", "shared-key")
    monkeypatch.setenv("LNBITS_LIVE_INVOICE_KEY", "shared-key")
    assert build_provider("alby_sandbox").network == "sandbox"


@pytest.mark.asyncio
async def test_status_requires_faucet_wallet_identities_and_methods(monkeypatch):
    provider, wallets = configured(monkeypatch)
    wallets[BUYER].get_info = lambda: asyncio.sleep(0, result={"alias": "nwc111", "methods": ["get_info"]})
    with pytest.raises(AlbySandboxError, match="missing required NWC methods"):
        await provider.status()


@pytest.mark.asyncio
async def test_status_checks_wallet_alias_separation(monkeypatch):
    provider, wallets = configured(monkeypatch)
    provider.merchant_uri = MERCHANT.replace("nwc222", "nwc111")
    from urllib.parse import urlparse
    provider.client_factory = lambda uri, **_kwargs: wallets[BUYER] if urlparse(uri).netloc == BUYER_PUBKEY else wallets[MERCHANT]
    with pytest.raises(AlbySandboxError, match="must be different"):
        await provider.status()


@pytest.mark.asyncio
async def test_faucet_identity_comes_from_distinct_lud16_when_hub_alias_is_generic(monkeypatch):
    provider, _ = configured(monkeypatch)
    status = await provider.status()
    assert status["buyer_wallet"]["alias"] == "nwc111"
    assert status["merchant_wallet"]["alias"] == "nwc222"


@pytest.mark.asyncio
async def test_balance_converts_exact_msat_without_rounding(monkeypatch):
    provider, _ = configured(monkeypatch)
    assert await provider.balance("buyer") == {"balance_msat": 12345, "balance_sats": 12.345, "wallet": "buyer", "environment": "sandbox"}


@pytest.mark.asyncio
async def test_invoice_uses_merchant_wallet_and_exact_msat_amount(monkeypatch):
    provider, wallets = configured(monkeypatch)
    invoice, created = await provider.create_invoice(10, "Order", expiry=600)
    assert invoice.payment_hash == PAYMENT_HASH
    assert invoice.network == "sandbox"
    assert wallets[MERCHANT].amount_msat == 10_000
    assert wallets[MERCHANT].invoice_kwargs == {"description": "Order", "expiry": 600}
    assert created == datetime.fromtimestamp(1_800_000_000, timezone.utc)
    wallets[MERCHANT].invoice_result["amount"] = 9_999
    with pytest.raises(AlbySandboxError, match="wrong-amount"):
        await provider.create_invoice(10, "Order")
    with pytest.raises(AlbySandboxError, match="positive whole number"):
        await provider.create_invoice(0, "bad")


@pytest.mark.asyncio
async def test_invoice_verification_checks_hash_amount_and_expiry(monkeypatch):
    provider, wallets = configured(monkeypatch)
    assert (await provider.verify_invoice(PAYMENT_HASH, 10)).status == "PENDING"
    wallets[MERCHANT].lookup_result["settled_at"] = 1_800_000_001
    assert (await provider.verify_invoice(PAYMENT_HASH, 10)).status == "PAID"
    wallets[MERCHANT].lookup_result["payment_hash"] = "b" * 64
    assert (await provider.verify_invoice(PAYMENT_HASH, 10)).status == "FAILED"
    wallets[MERCHANT].lookup_result = {"payment_hash": "hash-1", "amount": 9_999, "type": "incoming"}
    assert (await provider.verify_invoice(PAYMENT_HASH, 10)).status == "FAILED"
    wallets[MERCHANT].lookup_result = {"payment_hash": PAYMENT_HASH, "amount": 10_000, "expires_at": 1, "type": "incoming"}
    assert (await provider.verify_invoice(PAYMENT_HASH, 10)).status == "EXPIRED"


@pytest.mark.asyncio
async def test_pay_uses_buyer_wallet_and_confirms_against_merchant(monkeypatch):
    provider, wallets = configured(monkeypatch)
    async def paid(invoice, **kwargs):
        wallets[BUYER].pay_calls += 1
        wallets[MERCHANT].lookup_result["settled_at"] = 1_800_000_001
        return {"preimage": "buyer-result"}
    wallets[BUYER].pay_invoice = paid
    result = await provider.pay_invoice(wallets[MERCHANT].invoice_result["invoice"], PAYMENT_HASH, 10)
    assert result.status == "PAID"
    assert wallets[BUYER].pay_calls == 1
    assert wallets[MERCHANT].lookup_args == {"payment_hash": PAYMENT_HASH}


@pytest.mark.asyncio
async def test_insufficient_balance_and_ambiguous_relay_timeout_never_retry(monkeypatch):
    from aionwc import NWCWalletError, NWCRelayError
    provider, wallets = configured(monkeypatch)
    wallets[BUYER].pay_error = NWCWalletError("INSUFFICIENT_BALANCE", "secret must not escape")
    with pytest.raises(AlbySandboxError, match="insufficient test balance") as error:
        await provider.pay_invoice(wallets[MERCHANT].invoice_result["invoice"], PAYMENT_HASH, 10)
    assert "secret" not in str(error.value)
    assert wallets[BUYER].pay_calls == 1
    wallets[BUYER].pay_error = NWCRelayError("disconnect", request_id="request-1")
    with pytest.raises(AlbySandboxError, match="result is unknown") as error:
        await provider.pay_invoice(wallets[MERCHANT].invoice_result["invoice"], PAYMENT_HASH, 10)
    assert error.value.ambiguous
    assert wallets[BUYER].pay_calls == 2


@pytest.mark.asyncio
async def test_transaction_history_uses_documented_list_result(monkeypatch):
    provider, wallets = configured(monkeypatch)
    rows = await provider.transactions("buyer", 4)
    assert rows[0]["amount_msat"] == -2500
    assert rows[0]["amount_sats"] == -2.5
    assert rows[0]["mode"] == "alby_sandbox"
    assert wallets[BUYER].transaction_kwargs == {"limit": 4}


@pytest.mark.asyncio
async def test_service_persists_safe_wallet_aliases_and_completes_only_after_merchant_verification():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database import Base
    from models import PaymentInvoice, Transaction
    from services.lightning_service import LightningService
    from services.payment_providers import ProviderInvoice, ProviderPayment

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    class FakeProvider:
        async def status(self):
            return {"buyer_wallet": {"alias": "nwc111"}, "merchant_wallet": {"alias": "nwc222"}}

        async def create_invoice(self, amount, description):
            assert amount == 7
            return ProviderInvoice("lnbc7n1" + "a" * 80, "safe-hash", "safe-hash", "sandbox", None), datetime.now(timezone.utc)

        async def verify_invoice(self, payment_hash, amount, bolt11):
            assert (payment_hash, amount, bolt11) == ("safe-hash", 7, "lnbc7n1" + "a" * 80)
            return ProviderPayment("PAID", 7, "safe-hash", "safe-hash")

    service = LightningService(mode="alby_sandbox", provider_factory=lambda _mode: FakeProvider())
    inv = await service.create_invoice_async(7, "test order", db=db)
    tx = db.query(Transaction).filter(Transaction.invoice_id == inv.id).one()
    assert inv.amount_msat == tx.amount_msat == 7000
    assert (inv.buyer_wallet_alias, inv.merchant_wallet_alias) == ("nwc111", "nwc222")
    assert (tx.buyer_wallet_alias, tx.merchant_wallet_alias) == ("nwc111", "nwc222")
    assert "secret" not in repr(inv.__dict__) and "secret" not in repr(tx.__dict__)
    assert inv.status == "PENDING" and tx.status == "PAYMENT_PENDING"
    checked = await service.check_payment_async(inv.invoice_id, db)
    assert checked.status == "PAID" and checked.verified_at is not None
    assert tx.status == "COMPLETED"
    engine.dispose()


@pytest.mark.asyncio
async def test_ambiguous_payment_attempt_is_persisted_and_duplicate_endpoint_call_is_blocked(monkeypatch):
    import sys
    from pathlib import Path
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from database import Base
    from models import Negotiation, PaymentInvoice, User
    from routers import lightning as routes
    from schemas import PaymentApprovalRequest

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    buyer = User(username="nwc-buyer", email="nwc@example.com", password_hash="test", role="CUSTOMER")
    db.add(buyer)
    db.commit()
    negotiation = Negotiation(session_id="nwc-test", buyer_user_id=buyer.id, buyer_budget_sats=20, final_price_sats=10, approved_by_customer=True)
    db.add(negotiation)
    db.commit()
    inv = PaymentInvoice(invoice_id="invoice-unknown", negotiation_id=negotiation.id, payment_hash="hash", checking_id="hash", bolt11="lnbc10n1" + "a" * 80, amount_sats=10, amount_msat=10000, payment_mode="alby_sandbox", provider_name="alby_nwc_sandbox", environment="sandbox", is_demo=False, status="PENDING")
    db.add(inv)
    db.commit()

    class ServiceStub:
        async def check_payment_async(self, invoice_id, session):
            return session.query(PaymentInvoice).filter_by(invoice_id=invoice_id).one()

    class ProviderStub:
        pay_calls = 0
        async def pay_invoice(self, *_args):
            self.pay_calls += 1
            raise AlbySandboxError("PAYMENT_UNKNOWN", "timeout", ambiguous=True)

    provider = ProviderStub()
    monkeypatch.setattr(routes, "active_payment_mode", lambda: "alby_sandbox")
    monkeypatch.setattr(routes, "lightning_service", ServiceStub())
    monkeypatch.setattr(routes, "build_provider", lambda _mode: provider)
    with pytest.raises(HTTPException) as timeout:
        await routes.pay_invoice(inv.invoice_id, PaymentApprovalRequest(approve=True), db, buyer)
    assert timeout.value.status_code == 503
    db.refresh(inv)
    assert inv.status == "PAYMENT_UNKNOWN" and inv.payment_attempted_at is not None
    with pytest.raises(HTTPException) as duplicate:
        await routes.pay_invoice(inv.invoice_id, PaymentApprovalRequest(approve=True), db, buyer)
    assert duplicate.value.status_code == 409
    assert provider.pay_calls == 1
    engine.dispose()
