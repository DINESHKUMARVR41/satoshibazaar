"""Password hashing, signed access tokens, and route authorization."""
import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserSession

ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
_secret = os.getenv("JWT_SECRET", "").strip()
if not _secret or _secret.startswith("replace-with-"):
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise RuntimeError("JWT_SECRET must be configured in production.")
    _secret = secrets.token_urlsafe(48)
    warnings.warn("JWT_SECRET is unset; using an ephemeral local-development key.", RuntimeWarning)
JWT_SECRET = _secret

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def issue_access_token(user: User, db: Session) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    token_id = secrets.token_urlsafe(24)
    db.add(UserSession(
        token_id=token_id,
        user_id=user.id,
        expires_at=expires,
        created_at=now,
    ))
    db.commit()
    return jwt.encode({
        "sub": str(user.id),
        "role": user.role,
        "jti": token_id,
        "iat": now,
        "exp": expires,
    }, JWT_SECRET, algorithm=ALGORITHM)


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(claims.get("sub", ""))
        token_id = claims.get("jti")
        role = claims.get("role")
    except (JWTError, TypeError, ValueError):
        raise unauthorized
    session = db.query(UserSession).filter(
        UserSession.token_id == token_id,
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > datetime.now(timezone.utc),
    ).first()
    user = db.query(User).filter(User.id == user_id).first()
    if not session or not user or user.role != role:
        raise unauthorized
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return dependency


def revoke_access_token(token: str, db: Session) -> None:
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return
    session = db.query(UserSession).filter(UserSession.token_id == claims.get("jti")).first()
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
