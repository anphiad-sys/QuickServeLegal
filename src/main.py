"""
QuickServe Legal - Main Application Entry Point

Electronic service of legal documents with verified receipt confirmation.
"""

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR, STATIC_DIR
from src.database import init_db, close_db, get_db
from src.auth import get_current_user
from src.csrf import CSRFMiddleware
from src.rate_limit import RateLimitMiddleware
from src.routes.auth_routes import router as auth_router
from src.routes.document_routes import router as document_router
from src.routes.signing_routes import router as signing_router
from src.routes.certificate_routes import router as certificate_router
from src.routes.audit_routes import router as audit_router
from src.routes.webhook_routes import router as webhook_router
from src.routes.pnsa_routes import router as pnsa_router
from src.documents import get_user_sent_documents, get_user_received_documents, get_document_stats

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
)

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Add CSRF protection middleware
app.add_middleware(CSRFMiddleware)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Include routers
app.include_router(auth_router)
app.include_router(document_router)
app.include_router(signing_router)
app.include_router(certificate_router)
app.include_router(audit_router)
app.include_router(webhook_router)
app.include_router(pnsa_router)  # PNSA branch portal


# =============================================================================
# ROUTES
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """User dashboard - requires authentication."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/dashboard", status_code=303)

    # Get user's documents
    sent_documents = await get_user_sent_documents(db, user.id, limit=10)
    received_documents = await get_user_received_documents(db, user.email, limit=10)

    # Calculate stats
    stats = get_document_stats(sent_documents)
    stats["received"] = len(received_documents)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "stats": stats,
            "recent_documents": sent_documents[:5],
        }
    )


# =============================================================================
# STARTUP & SHUTDOWN
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    # Initialize database tables
    await init_db()

    print(f"""
    ==============================================================
    QuickServe Legal is starting...

    Version: {settings.APP_VERSION}
    URL: {settings.BASE_URL}
    Docs: {settings.BASE_URL}/docs
    ==============================================================
    """)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    await close_db()
    print(f"\nQuickServe Legal is shutting down...\n")


# =============================================================================
# RUN (for development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
