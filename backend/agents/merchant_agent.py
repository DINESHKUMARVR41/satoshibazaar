from sqlalchemy.orm import Session
from models import Product, Merchant
from agents.communication import comm_service


class MerchantAgent:
    def get_offer(self, merchant_id: int, product_id: int, buyer_request: dict, db: Session, conversation_id: str):
        product = db.query(Product).filter(Product.id == product_id).first()
        merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()

        if not product or not merchant:
            return None, []

        quantity = buyer_request.get("quantity_value", 1)
        unit_price = product.price_sats
        total_price = int(unit_price * quantity)
        offer = {
            "merchant_id": merchant.id,
            "product_id": product.id,
            "merchant_name": merchant.name,
            "product_name": product.name,
            "asking_price_sats": total_price,
            "unit_price_sats": unit_price,
            "total_price_sats": total_price,
            "requested_quantity": quantity,
            "requested_unit": buyer_request.get("unit", "unit"),
            "quantity_available": product.quantity_available,
            "can_negotiate": True,
            "is_demo": product.is_demo
        }

        msg = comm_service.create_message(
            sender="merchant_agent",
            recipient="negotiation_agent",
            message_type="merchant_offer",
            payload=offer,
            conversation_id=conversation_id
        )
        comm_service.save_message(db, msg)
        return offer, [msg]


merchant_agent = MerchantAgent()
