import uuid
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Merchant, Product, NostrListing, Transaction, Negotiation


def run_seed(db: Session):
    # Only seed if no merchants exist
    if db.query(Merchant).count() > 0:
        # Migrate the original demo catalog's mislabeled 25kg bags to per-kg
        # listings without touching merchant-created products or other stock.
        demo_rice = {
            "Community Grocery": (28000, 50, "Premium long-grain white rice, price per kg"),
            "Fresh Market Hub": (27000, 30, "High-quality imported rice, price per kg"),
            "BioFarm Direct": (24000, 20, "Organic local rice, price per kg"),
        }
        changed = False
        for merchant_name, (price, stock, description) in demo_rice.items():
            product = db.query(Product).join(Merchant).filter(
                Merchant.name == merchant_name,
                Product.name == "Rice 25kg",
                Product.is_demo.is_(True),
                Product.price_sats == price,
            ).first()
            if product:
                product.name = "Rice 1kg"
                product.quantity_available = stock
                product.description = description
                changed = True
        if changed:
            db.commit()
        return

    # --- Merchants ---
    merchants_data = [
        {
            "name": "Community Grocery",
            "description": "Your local community grocery store with fresh produce and staples.",
            "location": "Dakar, Senegal",
            "pubkey": "0001demo00000000000000000000000000000000000000000000000000001",
            "nostr_relay": "wss://relay.damus.io",
            "is_demo": True
        },
        {
            "name": "Fresh Market Hub",
            "description": "Wide variety of fresh market products at competitive prices.",
            "location": "Dakar, Senegal",
            "pubkey": "0002demo00000000000000000000000000000000000000000000000000002",
            "nostr_relay": "wss://relay.damus.io",
            "is_demo": True
        },
        {
            "name": "BioFarm Direct",
            "description": "Organic and biodynamic farm products direct from Thiès.",
            "location": "Thiès, Senegal",
            "pubkey": "0003demo00000000000000000000000000000000000000000000000000003",
            "nostr_relay": "wss://relay.damus.io",
            "is_demo": True
        },
    ]

    db_merchants = []
    for m in merchants_data:
        merchant = Merchant(**m, created_at=datetime.now(timezone.utc))
        db.add(merchant)
        db_merchants.append(merchant)
    db.commit()
    for m in db_merchants:
        db.refresh(m)

    # --- Products ---
    products_data = [
        # Merchant 0: Community Grocery
        {"merchant_idx": 0, "name": "Rice 1kg", "category": "Grains", "price_sats": 28000, "quantity_available": 50, "description": "Premium long-grain white rice, price per kg"},
        {"merchant_idx": 0, "name": "Tomatoes 1kg", "category": "Vegetables", "price_sats": 5000, "quantity_available": 50, "description": "Fresh ripe tomatoes, 1kg"},
        {"merchant_idx": 0, "name": "Sugar 1kg", "category": "Staples", "price_sats": 3000, "quantity_available": 100, "description": "Refined white sugar, 1kg"},
        {"merchant_idx": 0, "name": "Millet 10kg", "category": "Grains", "price_sats": 15000, "quantity_available": 30, "description": "Local millet, 10kg bag"},
        # Merchant 1: Fresh Market Hub
        {"merchant_idx": 1, "name": "Rice 1kg", "category": "Grains", "price_sats": 27000, "quantity_available": 30, "description": "High-quality imported rice, price per kg"},
        {"merchant_idx": 1, "name": "Tomatoes 1kg", "category": "Vegetables", "price_sats": 4500, "quantity_available": 40, "description": "Market-fresh tomatoes, 1kg"},
        {"merchant_idx": 1, "name": "Sugar 1kg", "category": "Staples", "price_sats": 2800, "quantity_available": 80, "description": "White granulated sugar, 1kg"},
        {"merchant_idx": 1, "name": "Millet 10kg", "category": "Grains", "price_sats": 14000, "quantity_available": 25, "description": "Traditional millet, 10kg"},
        # Merchant 2: BioFarm Direct
        {"merchant_idx": 2, "name": "Rice 1kg", "category": "Grains", "price_sats": 24000, "quantity_available": 20, "description": "Organic local rice, price per kg"},
        {"merchant_idx": 2, "name": "Tomatoes 1kg", "category": "Vegetables", "price_sats": 4200, "quantity_available": 60, "description": "Organic tomatoes from Thiès, 1kg"},
        {"merchant_idx": 2, "name": "Sugar 1kg", "category": "Staples", "price_sats": 2600, "quantity_available": 120, "description": "Unrefined cane sugar, 1kg"},
        {"merchant_idx": 2, "name": "Millet 10kg", "category": "Grains", "price_sats": 13500, "quantity_available": 35, "description": "Organic millet, 10kg"},
    ]

    db_products = []
    for pd in products_data:
        merchant = db_merchants[pd["merchant_idx"]]
        product = Product(
            merchant_id=merchant.id,
            name=pd["name"],
            category=pd["category"],
            price_sats=pd["price_sats"],
            quantity_available=pd["quantity_available"],
            description=pd["description"],
            is_demo=True,
            created_at=datetime.now(timezone.utc)
        )
        db.add(product)
        db_products.append(product)
    db.commit()
    for p in db_products:
        db.refresh(p)

    # --- Nostr Listings ---
    import hashlib, time
    for p in db_products:
        merchant = db.query(Merchant).filter(Merchant.id == p.merchant_id).first()
        content = json.dumps({
            "schema": "satoshibazaar/listing/v1",
            "merchant_name": merchant.name,
            "product": p.name,
            "category": p.category,
            "price_sats": p.price_sats,
            "quantity_available": p.quantity_available,
            "location": merchant.location,
            "is_demo": True
        })
        event_id = hashlib.sha256(f"{merchant.pubkey}{p.name}{p.price_sats}".encode()).hexdigest()
        listing = NostrListing(
            event_id=event_id,
            pubkey=merchant.pubkey,
            kind=30078,
            content=content,
            tags=json.dumps([["t", "satoshibazaar"], ["location", merchant.location]]),
            relay_url="wss://relay.damus.io",
            is_valid=False,
            created_at=datetime.now(timezone.utc)
        )
        db.add(listing)
    db.commit()

    # --- Demo Negotiations ---
    neg1 = Negotiation(
        session_id=str(uuid.uuid4()),
        merchant_id=db_merchants[2].id,
        product_id=db_products[8].id,  # BioFarm Rice
        buyer_budget_sats=25000,
        initial_offer_sats=24000,
        final_price_sats=24000,
        rounds=json.dumps([{
            "merchant_id": db_merchants[2].id,
            "merchant_name": "BioFarm Direct",
            "initial_asking": 24000,
            "final_price": 24000,
            "accepted": True,
            "rounds": [{"round": 1, "buyer_offer": 25000, "merchant_offer": 24000, "action": "accepted", "reasoning": "Price within budget"}]
        }]),
        status="accepted",
        approved_by_customer=True,
        created_at=datetime.now(timezone.utc)
    )
    neg2 = Negotiation(
        session_id=str(uuid.uuid4()),
        merchant_id=db_merchants[1].id,
        product_id=db_products[5].id,  # Fresh Market Tomatoes
        buyer_budget_sats=4000,
        initial_offer_sats=4500,
        final_price_sats=4200,
        rounds=json.dumps([{
            "merchant_id": db_merchants[1].id,
            "merchant_name": "Fresh Market Hub",
            "initial_asking": 4500,
            "final_price": 4200,
            "accepted": True,
            "rounds": [
                {"round": 1, "buyer_offer": 4250, "merchant_offer": 4500, "action": "counter_proposed", "reasoning": "Counter at midpoint"},
                {"round": 2, "buyer_offer": 4250, "merchant_offer": 4365, "action": "counter_accepted", "reasoning": "Merchant reduced to 97%"}
            ]
        }]),
        status="accepted",
        approved_by_customer=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(neg1)
    db.add(neg2)
    db.commit()

    # --- Demo Transactions ---
    tx_data = [
        {"merchant_name": "BioFarm Direct", "product_name": "Rice 25kg", "amount_sats": 24000, "status": "COMPLETED"},
        {"merchant_name": "Fresh Market Hub", "product_name": "Tomatoes 1kg", "amount_sats": 4200, "status": "COMPLETED"},
        {"merchant_name": "Community Grocery", "product_name": "Sugar 1kg", "amount_sats": 2800, "status": "COMPLETED"},
    ]
    for td in tx_data:
        tx = Transaction(
            tx_ref=f"DEMO-{uuid.uuid4().hex[:8].upper()}",
            merchant_name=td["merchant_name"],
            product_name=td["product_name"],
            amount_sats=td["amount_sats"],
            payment_method="lightning",
            status=td["status"],
            mode="demo",
            verification_status="verified",
            created_at=datetime.now(timezone.utc)
        )
        db.add(tx)
    db.commit()
