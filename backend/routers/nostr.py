import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_roles
from database import get_db
from models import Merchant, NostrListing, Product, User
from schemas import NostrPublishRequest
from services.nostr_service import nostr_service, _is_listing

router = APIRouter(prefix="/api/nostr", tags=["nostr"])


@router.get("/status")
def nostr_status():
    return nostr_service.status(probe=True)


@router.get("/merchants")
def nostr_merchants(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 100))
    events, relay_states = nostr_service.fetch_events(limit)
    for event in events:
        listing = db.query(NostrListing).filter(NostrListing.event_id == event["id"]).first()
        if not listing:
            relay = next((state["relay"] for state in relay_states if state.get("connected")), "")
            listing = NostrListing(
                event_id=event["id"],
                pubkey=event["pubkey"],
                kind=event["kind"],
                content=event["content"],
                tags=json.dumps(event["tags"], ensure_ascii=False),
                created_at=datetime.fromtimestamp(event["created_at"], timezone.utc),
                relay_url=relay,
                is_valid=True,
            )
            db.add(listing)
    if events:
        db.commit()
    return {"events": events, "relays": relay_states, "count": len(events), "source": "nostr_relay"}


@router.get("/listings/unsigned")
def unsigned_listing(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.merchant or product.merchant.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Product not found")
    return nostr_service.build_unsigned_listing(
        {"name": product.merchant.name, "location": product.merchant.location},
        {"id": product.id, "name": product.name, "category": product.category, "price_sats": product.price_sats, "quantity_available": product.quantity_available},
    )


@router.post("/publish")
def publish_listing(request: NostrPublishRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product or not product.merchant or product.merchant.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Product not found")
    event = request.event.model_dump()
    valid, reason = nostr_service.validate_event(event)
    if not valid:
        raise HTTPException(status_code=422, detail={"error": "Invalid signed Nostr event", "reason": reason})
    event_age = datetime.now(timezone.utc).timestamp() - event["created_at"]
    if event["kind"] != 30078 or event_age > 600 or event_age < -60:
        raise HTTPException(status_code=422, detail="Event must be a recent kind 30078 product listing")
    if product.merchant.pubkey and product.merchant.pubkey != event["pubkey"]:
        raise HTTPException(status_code=403, detail="Signed event key does not match this merchant profile")
    try:
        content = json.loads(event["content"])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Listing content must be valid JSON") from exc
    expected = {
        "schema": "satoshibazaar/listing/v1",
        "merchant_name": product.merchant.name,
        "product": product.name,
        "category": product.category,
        "price_sats": product.price_sats,
        "quantity_available": product.quantity_available,
        "location": product.merchant.location,
    }
    if content != expected or not _is_listing(event):
        raise HTTPException(status_code=422, detail="Signed listing content does not match the saved product")
    if not any(tag[0] == "d" and tag[1] == f"satoshibazaar-product-{product.id}" for tag in event["tags"] if len(tag) >= 2):
        raise HTTPException(status_code=422, detail="Listing is missing its product identifier tag")
    acknowledgements = nostr_service.publish_event(event)
    accepted = [ack for ack in acknowledgements if ack.get("acknowledged")]
    if not accepted:
        raise HTTPException(status_code=502, detail={"error": "No configured relay acknowledged the event", "relays": acknowledgements})
    product.merchant.pubkey = event["pubkey"]
    product.nostr_event_id = event["id"]
    db.merge(NostrListing(
        event_id=event["id"],
        pubkey=event["pubkey"],
        kind=event["kind"],
        content=event["content"],
        tags=json.dumps(event["tags"], ensure_ascii=False),
        created_at=datetime.fromtimestamp(event["created_at"], timezone.utc),
        relay_url=",".join(ack["relay"] for ack in accepted),
        is_valid=True,
    ))
    db.commit()
    return {"published": True, "event_id": event["id"], "acknowledgements": acknowledgements}
