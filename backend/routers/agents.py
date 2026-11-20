from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from schemas import AgentRunRequest, AgentSessionOut, AgentMessageOut
from models import AgentSession, AgentMessage
from agents import run_full_pipeline
from typing import List
import json
from auth import get_current_user, require_roles
from models import User

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/run")
def run_agents(request: AgentRunRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("CUSTOMER"))):
    result = run_full_pipeline(request.query, request.location, db, user_id=user.id)
    # Convert messages to serializable format
    result["messages"] = [
        {k: v for k, v in m.items()} if isinstance(m, dict) else {
            "message_id": m.message_id,
            "sender_agent": m.sender_agent,
            "recipient_agent": m.recipient_agent,
            "message_type": m.message_type,
            "payload": json.loads(m.payload) if isinstance(m.payload, str) else m.payload,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in result["messages"]
    ]
    return result


@router.get("/sessions", response_model=List[AgentSessionOut])
def list_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(AgentSession).filter(AgentSession.user_id == user.id).order_by(AgentSession.created_at.desc()).limit(50).all()


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(AgentSession).filter(AgentSession.session_id == session_id, AgentSession.user_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owner = db.query(AgentSession).filter(AgentSession.session_id == session_id, AgentSession.user_id == user.id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = db.query(AgentMessage).filter(
        AgentMessage.conversation_id == session_id
    ).order_by(AgentMessage.created_at).all()
    return [
        {
            "message_id": m.message_id,
            "conversation_id": m.conversation_id,
            "sender_agent": m.sender_agent,
            "recipient_agent": m.recipient_agent,
            "message_type": m.message_type,
            "payload": json.loads(m.payload) if m.payload else {},
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in messages
    ]
