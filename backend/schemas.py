from pydantic import BaseModel, Field, EmailStr, StringConstraints
from typing import Optional, List, Any, Literal, Annotated
from datetime import datetime


class MerchantCreate(BaseModel):
    name: str
    description: str = ""
    location: str = ""
    pubkey: str = ""
    nostr_relay: str = ""
    is_demo: bool = True


class AuthRegister(BaseModel):
    email: EmailStr
    username: Annotated[str, StringConstraints(min_length=3, max_length=40, strip_whitespace=True)]
    password: Annotated[str, StringConstraints(min_length=10, max_length=72)]
    role: Literal["CUSTOMER", "MERCHANT"] = "CUSTOMER"


class AuthLogin(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=72)]


class NostrSignedEvent(BaseModel):
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: List[List[str]]
    content: str
    sig: str


class NostrPublishRequest(BaseModel):
    product_id: int
    event: NostrSignedEvent


class MerchantOut(BaseModel):
    id: int
    name: str
    description: str
    location: str
    pubkey: str
    nostr_relay: str
    is_demo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    merchant_id: int
    name: str
    category: str = "General"
    price_sats: int
    quantity_available: int
    description: str = ""
    is_demo: bool = True


class ProductOut(BaseModel):
    id: int
    merchant_id: int
    name: str
    category: str
    price_sats: int
    quantity_available: int
    description: str
    is_demo: bool
    nostr_event_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MarketplaceItem(BaseModel):
    product_id: int
    product_name: str
    category: str
    price_sats: int
    quantity_available: int
    description: str
    merchant_id: int
    merchant_name: str
    merchant_location: str
    merchant_pubkey: str
    is_demo: bool
    listing_source: str


class AgentRunRequest(BaseModel):
    query: str
    location: str = "Dakar, Senegal"
    session_id: Optional[str] = None


class AgentSessionOut(BaseModel):
    id: int
    session_id: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    session_metadata: Optional[str] = Field(default=None, validation_alias="session_metadata")

    model_config = {"from_attributes": True}


class AgentMessageOut(BaseModel):
    id: int
    message_id: str
    conversation_id: str
    sender_agent: str
    recipient_agent: str
    message_type: str
    payload: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NegotiationOut(BaseModel):
    id: int
    session_id: str
    buyer_budget_sats: int
    initial_offer_sats: Optional[int]
    final_price_sats: Optional[int]
    rounds: Optional[str]
    status: str
    approved_by_customer: bool
    created_at: datetime
    completed_at: Optional[datetime]
    merchant_id: Optional[int]
    product_id: Optional[int]

    model_config = {"from_attributes": True}


class NegotiationApproveRequest(BaseModel):
    notes: Optional[str] = None


class InvoiceCreateRequest(BaseModel):
    negotiation_id: Optional[int] = None
    amount_sats: int
    description: str = ""
    # Kept optional for older clients; the backend-selected PAYMENT_MODE is authoritative.
    is_demo: Optional[bool] = None


class MerchantSettlementRequest(BaseModel):
    bolt11: Annotated[str, StringConstraints(min_length=30, max_length=2000)]


class InvoiceOut(BaseModel):
    id: int
    invoice_id: str
    payment_hash: Optional[str]
    bolt11: str
    amount_sats: int
    is_demo: bool
    status: str
    created_at: datetime
    expires_at: Optional[datetime]
    paid_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: int
    tx_ref: str
    merchant_name: str
    product_name: str
    amount_sats: int
    payment_method: str
    status: str
    mode: str
    verification_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskCheckOut(BaseModel):
    id: int
    check_type: str
    result: str
    details: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
