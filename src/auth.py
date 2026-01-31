"""
QuickServe Legal - Authentication Logic
"""

from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request, HTTPException, status

from src.config import settings
from src.models.user import User

# Session token serializer
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

# Session cookie name
SESSION_COOKIE_NAME = "quickserve_session"


# =============================================================================
# PASSWORD UTILITIES
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    ).hex()
    return f"{salt}${pwd_hash}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt, stored_hash = hashed_password.split('$')
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return secrets.compare_digest(pwd_hash, stored_hash)
    except ValueError:
        return False


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def create_session_token(user_id: int) -> str:
    """Create a secure session token for the user."""
    return serializer.dumps({"user_id": user_id})


def verify_session_token(token: str, max_age: int = None) -> Optional[dict]:
    """
    Verify and decode a session token.

    Args:
        token: The session token to verify
        max_age: Maximum age in seconds (defaults to ACCESS_TOKEN_EXPIRE_MINUTES)

    Returns:
        The decoded data if valid, None if invalid/expired
    """
    if max_age is None:
        max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    try:
        data = serializer.loads(token, max_age=max_age)
        return data
    except (BadSignature, SignatureExpired):
        return None


# =============================================================================
# USER OPERATIONS
# =============================================================================

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get a user by email address."""
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get a user by ID."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    firm_name: Optional[str] = None,
    phone: Optional[str] = None,
    attorney_reference: Optional[str] = None,
) -> User:
    """Create a new user account."""
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        firm_name=firm_name.strip() if firm_name else None,
        phone=phone.strip() if phone else None,
        attorney_reference=attorney_reference.strip() if attorney_reference else None,
        terms_accepted_at=datetime.utcnow(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user by email and password.

    Returns the user if authentication succeeds, None otherwise.
    """
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    """Update the user's last login timestamp."""
    user.last_login_at = datetime.utcnow()
    await db.commit()


# =============================================================================
# REQUEST AUTHENTICATION
# =============================================================================

async def get_current_user(request: Request, db: AsyncSession) -> Optional[User]:
    """
    Get the currently logged-in user from the session cookie.

    Returns None if not authenticated.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    data = verify_session_token(token)
    if not data:
        return None

    user_id = data.get("user_id")
    if not user_id:
        return None

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        return None

    return user


async def require_auth(request: Request, db: AsyncSession) -> User:
    """
    Require authentication - raises HTTPException if not logged in.

    Use this as a dependency for protected routes.
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login?next=" + str(request.url.path)}
        )
    return user
