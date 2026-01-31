"""
QuickServe Legal - Authentication Routes
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR
from src.database import get_db
from src.auth import (
    get_user_by_email,
    create_user,
    authenticate_user,
    update_last_login,
    create_session_token,
    get_current_user,
    SESSION_COOKIE_NAME,
)


router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# =============================================================================
# LOGIN
# =============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = "/dashboard",
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Display the login page."""
    # Redirect if already logged in
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url=next, status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "next": next,
            "error": error,
        }
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    db: AsyncSession = Depends(get_db),
):
    """Process login form submission."""
    user = await authenticate_user(db, email, password)

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "next": next,
                "error": "Invalid email or password",
                "email": email,  # Preserve email in form
            },
            status_code=400,
        )

    # Update last login time
    await update_last_login(db, user)

    # Create session and redirect
    token = create_session_token(user.id)
    response = RedirectResponse(url=next, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,  # Secure in production
    )
    return response


# =============================================================================
# REGISTER
# =============================================================================

@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Display the registration page."""
    # Redirect if already logged in
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
        }
    )


@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    full_name: str = Form(...),
    firm_name: str = Form(None),
    phone: str = Form(None),
    attorney_reference: str = Form(None),
    terms_accepted: str = Form(None),  # HTML forms send strings
    db: AsyncSession = Depends(get_db),
):
    """Process registration form submission."""
    errors = []

    # Convert terms_accepted to boolean (HTML forms send "true" or nothing)
    terms_accepted_bool = terms_accepted in ("true", "on", "1", "yes")

    # Validation
    if not terms_accepted_bool:
        errors.append("You must accept the Terms of Service")

    if password != password_confirm:
        errors.append("Passwords do not match")

    if len(password) < 8:
        errors.append("Password must be at least 8 characters")

    # Check if email already exists
    existing_user = await get_user_by_email(db, email)
    if existing_user:
        errors.append("An account with this email already exists")

    if errors:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "errors": errors,
                "email": email,
                "full_name": full_name,
                "firm_name": firm_name,
                "phone": phone,
                "attorney_reference": attorney_reference,
            },
            status_code=400,
        )

    # Create user
    user = await create_user(
        db=db,
        email=email,
        password=password,
        full_name=full_name,
        firm_name=firm_name,
        phone=phone,
        attorney_reference=attorney_reference,
    )

    # Log them in immediately
    token = create_session_token(user.id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
    )
    return response


# =============================================================================
# LOGOUT
# =============================================================================

@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    """Log the user out by clearing the session cookie."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# =============================================================================
# SELF-VERIFICATION (Development Mode Only)
# =============================================================================

@router.post("/verify-self")
async def verify_self(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Self-verify as an attorney (development mode only).
    In production, verification would be done by admin review.
    """
    # Only allow in DEBUG mode
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Not allowed in production")

    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Verify the user
    user.is_verified = True
    user.email_verified = True
    await db.commit()

    return RedirectResponse(url="/certificates?success=Account+verified+successfully", status_code=303)
