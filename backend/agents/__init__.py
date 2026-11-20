import uuid
from sqlalchemy.orm import Session
from models import AgentSession
from agents.buyer_agent import buyer_agent
from agents.discovery_agent import discovery_agent
from agents.merchant_agent import merchant_agent
from agents.negotiation_agent import negotiation_agent
from agents.risk_guardian import risk_guardian
from agents.communication import comm_service
import json
from datetime import datetime, timezone


def run_full_pipeline(query: str, location: str, db: Session, session_id: str = None, user_id: int = None):
    if not session_id:
        session_id = str(uuid.uuid4())

    conversation_id = session_id
    all_messages = []

    # Save session
    session_obj = AgentSession(
        session_id=session_id,
        user_id=user_id,
        status="running",
        created_at=datetime.now(timezone.utc),
        session_metadata=json.dumps({"query": query, "location": location})
    )
    db.add(session_obj)
    db.commit()

    # Step 1: Buyer Agent
    buyer_result, buyer_msgs = buyer_agent.run(query, location, db, conversation_id)
    all_messages.extend(buyer_msgs)

    # Step 2: Discovery Agent
    budget = buyer_result.get("budget_sats") or 100000
    merchants, disc_msgs = discovery_agent.discover(
        product=buyer_result.get("product", "rice"),
        location=buyer_result.get("location") or location,
        budget_sats=budget,
        db=db,
        conversation_id=conversation_id,
        quantity=buyer_result.get("quantity_value", 1)
    )
    all_messages.extend(disc_msgs)

    # Step 3: Merchant Agent - get offers for top 3
    offers = []
    for m_info in merchants[:3]:
        offer, m_msgs = merchant_agent.get_offer(
            merchant_id=m_info["merchant_id"],
            product_id=m_info["product_id"],
            buyer_request=buyer_result,
            db=db,
            conversation_id=conversation_id
        )
        if offer:
            offer["merchant_id"] = m_info["merchant_id"]
            offer["product_id"] = m_info["product_id"]
            offers.append(offer)
            all_messages.extend(m_msgs)

    # Step 4: Negotiation Agent
    neg_result, neg_msgs = negotiation_agent.negotiate(
        buyer_budget_sats=budget,
        offers_list=offers,
        db=db,
        conversation_id=conversation_id,
        session_id=session_id,
        user_id=user_id,
        quantity=buyer_result.get("quantity_value", 1),
        unit=buyer_result.get("unit", "unit")
    )
    all_messages.extend(neg_msgs)

    # Step 5: Risk Guardian pre-check
    neg_id = neg_result.get("negotiation_id")
    agreed_price = neg_result.get("agreed_price_sats") or budget
    is_valid, checks, warnings = risk_guardian.validate_transaction(neg_id, agreed_price, db, require_approval=False)

    risk_msg = comm_service.create_message(
        sender="risk_guardian",
        recipient="customer",
        message_type="risk_assessment",
        payload={"is_valid": is_valid, "checks": checks, "warnings": warnings, "awaiting_approval": True},
        conversation_id=conversation_id
    )
    comm_service.save_message(db, risk_msg)
    all_messages.append(risk_msg)

    # Update session
    session_obj.status = "completed"
    session_obj.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "session_id": session_id,
        "buyer_result": buyer_result,
        "merchants_found": merchants,
        "offers": offers,
        "negotiation": neg_result,
        "risk_assessment": {"is_valid": is_valid, "checks": checks, "warnings": warnings},
        "messages": all_messages,
        "status": "completed"
    }
