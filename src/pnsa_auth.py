"""
QuickServe Legal - PNSA Branch Operator Authentication

Separate authentication system for PNSA branch operators.
Mirrors the patterns in src/auth.py but for BranchOperator accounts.
"""

from datetime import datetime
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request, HTTPException, status

from src.config import settings
from src.auth import hash_password, verify_password  # Single source of truth
from src.models.branch_operator import BranchOperator
from src.models.branch import Branch


# Session token serializer (uses same secret key but different salt)
serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="pnsa-operator-session")

# Session cookie name (different from member session)
PNSA_SESSION_COOKIE = "pnsa_session"

# Session expiry (default 8 hours for branch operators)
PNSA_SESSION_EXPIRE_MINUTES = getattr(settings, 'PNSA_SESSION_EXPIRE_MINUTES', 480)


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def create_operator_session(operator_id: int, branch_id: int) -> str:
    """Create a secure session token for the branch operator."""
    return serializer.dumps({
        "operator_id": operator_id,
        "branch_id": branch_id,
    })


def verify_operator_session(token: str, max_age: int = None) -> Optional[dict]:
    """
    Verify and decode an operator session token.

    Args:
        token: The session token to verify
        max_age: Maximum age in seconds (defaults to PNSA_SESSION_EXPIRE_MINUTES)

    Returns:
        The decoded data if valid, None if invalid/expired
    """
    if max_age is None:
        max_age = PNSA_SESSION_EXPIRE_MINUTES * 60

    try:
        data = serializer.loads(token, max_age=max_age)
        return data
    except (BadSignature, SignatureExpired):
        return None


# =============================================================================
# OPERATOR OPERATIONS
# =============================================================================

async def get_operator_by_email(db: AsyncSession, email: str) -> Optional[BranchOperator]:
    """Get an operator by email address."""
    result = await db.execute(
        select(BranchOperator).where(BranchOperator.email == email.lower())
    )
    return result.scalar_one_or_none()


async def get_operator_by_id(db: AsyncSession, operator_id: int) -> Optional[BranchOperator]:
    """Get an operator by ID."""
    result = await db.execute(
        select(BranchOperator).where(BranchOperator.id == operator_id)
    )
    return result.scalar_one_or_none()


async def get_operator_by_employee_number(db: AsyncSession, employee_number: str) -> Optional[BranchOperator]:
    """Get an operator by employee number."""
    result = await db.execute(
        select(BranchOperator).where(BranchOperator.employee_number == employee_number)
    )
    return result.scalar_one_or_none()


async def create_operator(
    db: AsyncSession,
    branch_id: int,
    employee_number: str,
    email: str,
    password: str,
    full_name: str,
    phone: Optional[str] = None,
    role: str = "operator",
) -> BranchOperator:
    """Create a new branch operator account."""
    operator = BranchOperator(
        branch_id=branch_id,
        employee_number=employee_number.strip(),
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        phone=phone.strip() if phone else None,
        role=role,
    )
    db.add(operator)
    await db.commit()
    await db.refresh(operator)
    return operator


async def authenticate_operator(
    db: AsyncSession,
    email: str,
    password: str,
) -> Optional[BranchOperator]:
    """
    Authenticate an operator by email and password.

    Returns the operator if authentication succeeds, None otherwise.
    """
    operator = await get_operator_by_email(db, email)
    if not operator:
        return None
    if not verify_password(password, operator.password_hash):
        return None
    if not operator.is_active:
        return None
    return operator


async def update_operator_last_login(db: AsyncSession, operator: BranchOperator) -> None:
    """Update the operator's last login timestamp."""
    operator.last_login_at = datetime.utcnow()
    await db.commit()


# =============================================================================
# BRANCH OPERATIONS
# =============================================================================

async def get_branch_by_id(db: AsyncSession, branch_id: int) -> Optional[Branch]:
    """Get a branch by ID."""
    result = await db.execute(
        select(Branch).where(Branch.id == branch_id)
    )
    return result.scalar_one_or_none()


async def get_branch_by_code(db: AsyncSession, branch_code: str) -> Optional[Branch]:
    """Get a branch by branch code."""
    result = await db.execute(
        select(Branch).where(Branch.branch_code == branch_code.upper())
    )
    return result.scalar_one_or_none()


async def get_active_branches(db: AsyncSession) -> list[Branch]:
    """Get all active branches."""
    result = await db.execute(
        select(Branch).where(Branch.is_active == True).order_by(Branch.branch_name)
    )
    return list(result.scalars().all())


async def create_branch(
    db: AsyncSession,
    branch_code: str,
    branch_name: str,
    address: str,
    city: str,
    province: str,
    postal_code: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> Branch:
    """Create a new branch."""
    branch = Branch(
        branch_code=branch_code.upper().strip(),
        branch_name=branch_name.strip(),
        address=address.strip(),
        city=city.strip(),
        province=province.strip(),
        postal_code=postal_code.strip() if postal_code else None,
        phone=phone.strip() if phone else None,
        email=email.lower().strip() if email else None,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


# =============================================================================
# REQUEST AUTHENTICATION
# =============================================================================

async def get_current_operator(request: Request, db: AsyncSession) -> Optional[BranchOperator]:
    """
    Get the currently logged-in operator from the session cookie.

    Returns None if not authenticated.
    """
    token = request.cookies.get(PNSA_SESSION_COOKIE)
    if not token:
        return None

    data = verify_operator_session(token)
    if not data:
        return None

    operator_id = data.get("operator_id")
    if not operator_id:
        return None

    operator = await get_operator_by_id(db, operator_id)
    if not operator or not operator.is_active:
        return None

    return operator


async def require_operator_auth(request: Request, db: AsyncSession) -> BranchOperator:
    """
    Require operator authentication - raises HTTPException if not logged in.

    Use this as a dependency for protected PNSA routes.
    """
    operator = await get_current_operator(request, db)
    if not operator:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/pnsa/login?next=" + str(request.url.path)}
        )
    return operator


async def get_operator_with_branch(
    request: Request,
    db: AsyncSession,
) -> tuple[Optional[BranchOperator], Optional[Branch]]:
    """
    Get the current operator and their branch.

    Returns (None, None) if not authenticated.
    """
    operator = await get_current_operator(request, db)
    if not operator:
        return None, None

    branch = await get_branch_by_id(db, operator.branch_id)
    return operator, branch
