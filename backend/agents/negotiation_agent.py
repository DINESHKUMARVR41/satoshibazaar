import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Negotiation
from agents.communication import comm_service


class NegotiationAgent:
    MAX_ROUNDS = 3
    TOLERANCE = 0.0

    def negotiate(self, buyer_budget_sats: int, offers_list: list, db: Session, conversation_id: str, session_id: str = None, user_id: int = None, quantity: int = 1, unit: str = "unit"):
        rounds = []
        best_offer = None
        status = "rejected"
        agreed_price = None

        # Sort offers by price
        sorted_offers = sorted(offers_list, key=lambda x: x.get("asking_price_sats", 999999999))

        for offer in sorted_offers[:3]:  # Consider top 3 merchants
            asking = offer.get("asking_price_sats", 0)
            max_acceptable = int(buyer_budget_sats * (1 + self.TOLERANCE))

            round_records = []
            current_price = asking
            accepted = False

            for round_num in range(1, self.MAX_ROUNDS + 1):
                if current_price <= max_acceptable:
                    accepted = True
                    round_records.append({
                        "round": round_num,
                        "buyer_offer": buyer_budget_sats,
                        "merchant_offer": current_price,
                        "action": "accepted",
                        "reasoning": f"Total price {current_price} sats is within buyer budget of {buyer_budget_sats} sats"
                    })
                    break
                else:
                    # Counter at midpoint between budget and asking
                    counter = int((buyer_budget_sats + current_price) / 2)
                    round_records.append({
                        "round": round_num,
                        "buyer_offer": counter,
                        "merchant_offer": current_price,
                        "action": "counter_proposed",
                        "reasoning": f"Merchant asks {current_price}, buyer budget {buyer_budget_sats}. Proposing counter at {counter} sats"
                    })
                    # Merchant accepts if counter >= asking * 0.95
                    if counter >= asking * 0.95:
                        accepted = True
                        current_price = counter
                        round_records[-1]["action"] = "counter_accepted"
                        break
                    # Otherwise merchant slightly reduces
                    current_price = int(current_price * 0.97)

            rounds.append({
                "merchant_id": offer["merchant_id"],
                "merchant_name": offer["merchant_name"],
                "initial_asking": asking,
                "final_price": current_price if accepted else asking,
                "accepted": accepted,
                "rounds": round_records
            })

            if accepted and (best_offer is None or current_price < best_offer["final_price"]):
                best_offer = {
                    "merchant_id": offer["merchant_id"],
                    "merchant_name": offer["merchant_name"],
                    "product_id": offer["product_id"],
                    "product_name": offer["product_name"],
                    "final_price": current_price,
                    "initial_asking": asking
                }
                status = "accepted"
                agreed_price = current_price

        if status == "rejected" and sorted_offers:
            # Return best available even if over budget
            cheapest = sorted_offers[0]
            status = "best_available"
            agreed_price = cheapest["asking_price_sats"]
            best_offer = {
                "merchant_id": cheapest["merchant_id"],
                "merchant_name": cheapest["merchant_name"],
                "product_id": cheapest["product_id"],
                "product_name": cheapest["product_name"],
                "final_price": agreed_price,
                "initial_asking": agreed_price
            }

        # Save to database
        neg = None
        if best_offer:
            neg = Negotiation(
                session_id=session_id or conversation_id,
                buyer_user_id=user_id,
                merchant_id=best_offer.get("merchant_id"),
                product_id=best_offer.get("product_id"),
                buyer_budget_sats=buyer_budget_sats,
                requested_quantity=float(quantity),
                requested_unit=unit,
                initial_offer_sats=best_offer.get("initial_asking"),
                final_price_sats=agreed_price,
                rounds=json.dumps(rounds),
                status=status,
                approved_by_customer=False,
                created_at=datetime.now(timezone.utc)
            )
            db.add(neg)
            db.commit()
            db.refresh(neg)

        result = {
            "status": status,
            "agreed_price_sats": agreed_price,
            "best_merchant": best_offer,
            "all_rounds": rounds,
            "negotiation_id": neg.id if neg else None,
            "within_budget": agreed_price <= buyer_budget_sats if agreed_price else False
        }

        msg = comm_service.create_message(
            sender="negotiation_agent",
            recipient="risk_guardian",
            message_type="negotiation_result",
            payload=result,
            conversation_id=conversation_id
        )
        comm_service.save_message(db, msg)
        return result, [msg]


negotiation_agent = NegotiationAgent()
