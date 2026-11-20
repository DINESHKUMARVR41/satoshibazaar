from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    public_key = Column(String, default="")
    password_hash = Column(String, nullable=True)
    role = Column(String, nullable=False, default="CUSTOMER", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    location = Column(String, default="")
    pubkey = Column(String, default="")
    nostr_relay = Column(String, default="")
    is_demo = Column(Boolean, default=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    products = relationship("Product", back_populates="merchant")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, default="General")
    price_sats = Column(Integer, nullable=False)
    quantity_available = Column(Integer, default=0)
    description = Column(String, default="")
    is_demo = Column(Boolean, default=True)
    nostr_event_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    merchant = relationship("Merchant", back_populates="products")


class NostrListing(Base):
    __tablename__ = "nostr_listings"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, nullable=False)
    pubkey = Column(String, default="")
    kind = Column(Integer, default=30078)
    content = Column(Text, default="")
    tags = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    relay_url = Column(String, default="")
    is_valid = Column(Boolean, default=True)

    __table_args__ = (Index("ix_nostr_event_id", "event_id"),)


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String, default="running")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    session_metadata = Column("metadata", Text, default="{}")

    __table_args__ = (Index("ix_agent_session_id", "session_id"),)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, nullable=False)
    conversation_id = Column(String, nullable=False, index=True)
    sender_agent = Column(String, nullable=False)
    recipient_agent = Column(String, nullable=False)
    message_type = Column(String, nullable=False)
    payload = Column(Text, default="{}")
    status = Column(String, default="sent")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Negotiation(Base):
    __tablename__ = "negotiations"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    buyer_budget_sats = Column(Integer, nullable=False)
    requested_quantity = Column(Float, nullable=False, default=1)
    requested_unit = Column(String, default="unit")
    initial_offer_sats = Column(Integer, nullable=True)
    final_price_sats = Column(Integer, nullable=True)
    rounds = Column(Text, default="[]")
    status = Column(String, default="pending")
    approved_by_customer = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class PaymentInvoice(Base):
    __tablename__ = "payment_invoices"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(String, unique=True, nullable=False)
    negotiation_id = Column(Integer, ForeignKey("negotiations.id"), nullable=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True, index=True)
    payment_hash = Column(String, unique=True, nullable=True)
    checking_id = Column(String, unique=True, nullable=True)
    bolt11 = Column(Text, default="")
    amount_sats = Column(Integer, nullable=False)
    payment_mode = Column(String(12), nullable=False, default="demo", index=True)
    provider_name = Column(String(40), nullable=False, default="demo_simulator")
    environment = Column(String(16), nullable=False, default="demo")
    is_demo = Column(Boolean, default=True)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    amount_msat = Column(Integer, nullable=True)
    buyer_wallet_alias = Column(String(80), nullable=True)
    merchant_wallet_alias = Column(String(80), nullable=True)
    payment_attempted_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_invoice_id", "invoice_id"),)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    tx_ref = Column(String, unique=True, nullable=False)
    negotiation_id = Column(Integer, ForeignKey("negotiations.id"), nullable=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True, index=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    invoice_id = Column(Integer, ForeignKey("payment_invoices.id"), nullable=True)
    merchant_name = Column(String, default="")
    product_name = Column(String, default="")
    amount_sats = Column(Integer, nullable=False)
    payment_method = Column(String, default="lightning")
    status = Column(String, default="pending")
    mode = Column(String, default="demo")
    provider_name = Column(String(40), nullable=False, default="demo_simulator")
    environment = Column(String(16), nullable=False, default="demo")
    verification_status = Column(String, default="unverified")
    amount_msat = Column(Integer, nullable=True)
    buyer_wallet_alias = Column(String(80), nullable=True)
    merchant_wallet_alias = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("ix_tx_ref", "tx_ref"),)


class PaymentSettlement(Base):
    __tablename__ = "payment_settlements"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), unique=True, nullable=False, index=True)
    payment_mode = Column(String(12), nullable=False, index=True)
    network = Column(String(12), nullable=False)
    amount_sats = Column(Integer, nullable=False)
    merchant_invoice = Column(Text, nullable=False)
    payment_hash = Column(String(128), nullable=True)
    checking_id = Column(String(255), unique=True, nullable=True)
    status = Column(String(32), nullable=False, default="SUBMITTING")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime, nullable=True)


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    id = Column(Integer, primary_key=True, index=True)
    negotiation_id = Column(Integer, ForeignKey("negotiations.id"), unique=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="RESERVED", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime, nullable=True)


class RiskCheck(Base):
    __tablename__ = "risk_checks"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    check_type = Column(String, nullable=False)
    result = Column(String, nullable=False)
    details = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
