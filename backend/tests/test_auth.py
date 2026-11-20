import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from seed import run_seed  # noqa: E402
from models import Product, Merchant  # noqa: E402


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_register_login_me_and_logout_revoke_access(client):
    registration = client.post("/api/auth/register", json={
        "email": "buyer@example.com", "username": "buyer", "password": "safe-test-password-1", "role": "CUSTOMER",
    })
    assert registration.status_code == 201
    token = registration.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "CUSTOMER"

    login_response = client.post("/api/auth/login", json={"email": "buyer@example.com", "password": "safe-test-password-1"})
    assert login_response.status_code == 200
    assert client.post("/api/auth/login", json={"email": "buyer@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_customer_cannot_write_products_and_merchant_owns_profile(client):
    customer = client.post("/api/auth/register", json={
        "email": "customer@example.com", "username": "customer", "password": "safe-test-password-2", "role": "CUSTOMER",
    }).json()
    customer_headers = {"Authorization": f"Bearer {customer['access_token']}"}
    assert client.post("/api/merchants", headers=customer_headers, json={"name": "Nope"}).status_code == 403

    merchant = client.post("/api/auth/register", json={
        "email": "merchant@example.com", "username": "merchant", "password": "safe-test-password-3", "role": "MERCHANT",
    }).json()
    merchant_headers = {"Authorization": f"Bearer {merchant['access_token']}"}
    profile = client.post("/api/merchants", headers=merchant_headers, json={"name": "My Store", "location": "Dakar"})
    assert profile.status_code == 200
    merchant_id = profile.json()["id"]
    created = client.post("/api/products", headers=merchant_headers, json={
        "merchant_id": merchant_id, "name": "Rice", "price_sats": 20, "quantity_available": 4,
    })
    assert created.status_code == 200
    assert created.json()["is_demo"] is False
    assert client.put(f"/api/products/{created.json()['id']}", headers=customer_headers, json={
        "merchant_id": merchant_id, "name": "Changed", "price_sats": 1, "quantity_available": 99,
    }).status_code == 403


def test_authenticated_buyer_demo_purchase_reserves_stock_and_persists_nonpayable_invoice(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    registration = client.post("/api/auth/register", json={
        "email": "flow-buyer@example.com", "username": "flowbuyer", "password": "safe-test-password-4", "role": "CUSTOMER",
    }).json()
    headers = {"Authorization": f"Bearer {registration['access_token']}"}
    from database import SessionLocal

    # Use the dependency-override database seeded for this test's client.
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        run_seed(db)
        biofarm_rice = db.query(Product).join(Merchant).filter(Merchant.name == "BioFarm Direct", Product.name == "Rice 1kg").first()
        starting_stock = biofarm_rice.quantity_available
        product_id = biofarm_rice.id
    finally:
        db_generator.close()

    workflow = client.post("/api/agents/run", headers=headers, json={
        "query": "I need 10 kg of rice in Dakar for a maximum total of 250,000 sats.", "location": "Dakar, Senegal",
    })
    assert workflow.status_code == 200
    result = workflow.json()
    assert result["negotiation"]["best_merchant"]["merchant_name"] == "BioFarm Direct"
    assert result["negotiation"]["agreed_price_sats"] == 240000
    negotiation_id = result["negotiation"]["negotiation_id"]

    assert client.post(f"/api/negotiations/{negotiation_id}/approve", headers=headers).status_code == 200
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        assert db.query(Product).filter(Product.id == product_id).first().quantity_available == starting_stock - 10
    finally:
        db_generator.close()

    invoice = client.post("/api/lightning/invoices", headers=headers, json={
        "negotiation_id": negotiation_id, "amount_sats": 240000, "is_demo": True,
    })
    assert invoice.status_code == 200
    assert invoice.json()["bolt11"].startswith("DEMO-SIMULATED-NOT-PAYABLE-")
    duplicate_invoice = client.post("/api/lightning/invoices", headers=headers, json={
        "negotiation_id": negotiation_id, "amount_sats": 240000, "is_demo": True,
    })
    assert duplicate_invoice.status_code == 200
    assert duplicate_invoice.json()["invoice_id"] == invoice.json()["invoice_id"]
    transactions = client.get("/api/transactions", headers=headers).json()
    assert any(tx["amount_sats"] == 240000 and tx["status"] == "DEMO_INVOICE_CREATED" for tx in transactions)
    assert client.get(f"/api/negotiations/{negotiation_id}").status_code == 401


def test_alby_wallet_api_endpoints_are_authenticated_and_redact_credentials(client, monkeypatch):
    registration = client.post("/api/auth/register", json={
        "email": "wallet-buyer@example.com", "username": "walletbuyer", "password": "safe-test-password-9", "role": "CUSTOMER",
    }).json()
    headers = {"Authorization": f"Bearer {registration['access_token']}"}
    from routers import lightning

    class FakeWalletProvider:
        network = "sandbox"
        configured = True
        async def status(self):
            return {"connected": True, "mode": "alby_sandbox", "network": "sandbox", "buyer_wallet": {"alias": "nwc123"}, "merchant_wallet": {"alias": "nwc456"}}
        async def balance(self, wallet):
            return {"balance_msat": 12345, "balance_sats": 12.345, "wallet": wallet, "environment": "sandbox"}
        async def transactions(self, wallet="buyer"):
            return [{"type": "outgoing", "amount_msat": -1000, "amount_sats": -1, "status": "PAID"}]

    monkeypatch.setattr(lightning, "active_payment_mode", lambda: "alby_sandbox")
    monkeypatch.setattr(lightning, "build_provider", lambda _mode: FakeWalletProvider())
    assert client.get("/api/lightning/status").status_code == 401
    status = client.get("/api/lightning/status", headers=headers)
    assert status.status_code == 200 and status.json()["connected"]
    assert status.json()["buyer_wallet"]["alias"] == "nwc123"
    balance = client.get("/api/lightning/balance", headers=headers)
    assert balance.status_code == 200 and balance.json()["balance_msat"] == 12345
    history = client.get("/api/lightning/transactions", headers=headers)
    assert history.status_code == 200 and history.json()[0]["amount_msat"] == -1000
    serialized = status.text + balance.text + history.text
    assert "secret=" not in serialized and "nostr+walletconnect://" not in serialized
