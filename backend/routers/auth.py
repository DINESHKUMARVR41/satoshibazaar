from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password, issue_access_token, revoke_access_token, verify_password, oauth2_scheme
from database import get_db
from models import User
from schemas import AuthLogin, AuthRegister

router = APIRouter(prefix="/api/auth", tags=["auth"])
_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_attempt_lock = Lock()
_WINDOW = timedelta(minutes=1)
_MAX_ATTEMPTS = 8


def _check_rate_limit(request: Request):
    key = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    with _attempt_lock:
        attempts = _attempts[key]
        while attempts and attempts[0] < now - _WINDOW:
            attempts.popleft()
        if len(attempts) >= _MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many authentication attempts. Try again shortly.")
        attempts.append(now)


def _auth_response(user: User, db: Session):
    return {
        "access_token": issue_access_token(user, db),
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "username": user.username, "role": user.role},
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: AuthRegister, request: Request, db: Session = Depends(get_db)):
    _check_rate_limit(request)
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password must be at most 72 UTF-8 bytes for bcrypt")
    email = str(payload.email).lower()
    username = payload.username.strip()
    if db.query(User).filter(or_(User.email == email, User.username == username)).first():
        raise HTTPException(status_code=409, detail="Email or username is already registered")
    user = User(
        email=email,
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email or username is already registered") from exc
    db.refresh(user)
    return _auth_response(user, db)


@router.post("/login")
def login(payload: AuthLogin, request: Request, db: Session = Depends(get_db)):
    _check_rate_limit(request)
    user = db.query(User).filter(User.email == str(payload.email).lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    return _auth_response(user, db)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "username": user.username, "role": user.role}


@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    revoke_access_token(token, db)
    return {"logged_out": True}
