from sqlalchemy.orm import Session
from models import Product, Merchant
from agents.communication import comm_service


class MerchantDiscoveryAgent:
    def discover(self, product: str, location: str, budget_sats: int, db: Session, conversation_id: str, quantity: float = 1):
        budget_limit = int(budget_sats) if budget_sats else 10000000

        products = db.query(Product).join(Merchant).filter(
            Product.name.ilike(f"%{product}%")
        ).filter(
            Product.price_sats <= budget_limit
        ).filter(
            Product.quantity_available >= quantity
        ).all()

        merchants_found = []
        for p in products[:10]:
            m = db.query(Merchant).filter(Merchant.id == p.merchant_id).first()
            if m:
                merchants_found.append({
                    "merchant_id": m.id,
                    "merchant_name": m.name,
                    "pubkey": m.pubkey,
                    "location": m.location,
                    "product_id": p.id,
                    "product_name": p.name,
                    "price_sats": p.price_sats,
                    "quantity_available": p.quantity_available,
                    "is_demo": p.is_demo,
                    "listing_source": "demo_database" if p.is_demo else "nostr_relay",
                    "authentication_note": "Demo merchant — not cryptographically verified"
                })

        merchants_found.sort(key=lambda x: x["price_sats"])

        msg = comm_service.create_message(
            sender="discovery_agent",
            recipient="merchant_agent",
            message_type="merchants_found",
            payload={"count": len(merchants_found), "merchants": merchants_found, "product": product, "location": location},
            conversation_id=conversation_id
        )
        comm_service.save_message(db, msg)
        return merchants_found, [msg]


discovery_agent = MerchantDiscoveryAgent()
