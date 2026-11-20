import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import AgentMessage
import json


class AgentCommunicationService:
    def create_message(self, sender: str, recipient: str, message_type: str,
                       payload: dict, conversation_id: str) -> dict:
        return {
            "message_id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "sender_agent": sender,
            "recipient_agent": recipient,
            "message_type": message_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "status": "sent"
        }

    def save_message(self, db: Session, msg: dict) -> AgentMessage:
        db_msg = AgentMessage(
            message_id=msg["message_id"],
            conversation_id=msg["conversation_id"],
            sender_agent=msg["sender_agent"],
            recipient_agent=msg["recipient_agent"],
            message_type=msg["message_type"],
            payload=json.dumps(msg["payload"]),
            status=msg["status"],
            created_at=datetime.now(timezone.utc)
        )
        db.add(db_msg)
        db.commit()
        db.refresh(db_msg)
        return db_msg

    def get_conversation(self, db: Session, conversation_id: str):
        return db.query(AgentMessage).filter(
            AgentMessage.conversation_id == conversation_id
        ).order_by(AgentMessage.created_at).all()


comm_service = AgentCommunicationService()
