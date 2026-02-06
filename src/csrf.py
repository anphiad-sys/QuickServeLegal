"""
QuickServe Legal - CSRF Protection

Double-submit cookie pattern: A random token is set in both a cookie
and included as a hidden form field. On POST, both must match.

Uses a raw ASGI middleware to avoid the body-consumption issue with
BaseHTTPMiddleware.
"""

import secrets
from urllib.parse import parse_qs
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_TOKEN_LENGTH = 32

# Paths exempt from CSRF checking (webhooks, API endpoints)
CSRF_EXEMPT_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/webhook/sendgrid",
}

# Path prefixes exempt from CSRF (e.g., API docs)
CSRF_EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
)


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def get_csrf_token(request: Request) -> str:
    """Get the CSRF token from the cookie, or generate a new one."""
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
    return token


class CSRFMiddleware:
    """
    CSRF protection middleware using double-submit cookie pattern.

    Implemented as raw ASGI middleware to avoid consuming the request body.
    Reads the body, checks the CSRF token, then replays the body for downstream handlers.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        # Skip exempt paths
        if path in CSRF_EXEMPT_PATHS or path.startswith(CSRF_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            # For GET/HEAD etc, just ensure CSRF cookie is set
            response_started = False
            original_send = send

            async def send_with_cookie(message):
                nonlocal response_started
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    if CSRF_COOKIE_NAME not in request.cookies:
                        token = generate_csrf_token()
                        headers = list(message.get("headers", []))
                        cookie_value = f"{CSRF_COOKIE_NAME}={token}; Path=/; SameSite=Lax"
                        headers.append([b"set-cookie", cookie_value.encode()])
                        message = {**message, "headers": headers}
                await original_send(message)

            await self.app(scope, receive, send_with_cookie)
            return

        # For POST/PUT/DELETE/PATCH: validate CSRF token
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        if not cookie_token:
            response = JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing"},
            )
            await response(scope, receive, send)
            return

        # Check header first
        submitted_token = request.headers.get(CSRF_HEADER_NAME)

        if not submitted_token:
            # Need to read the body to get the form field
            body = b""
            while True:
                message = await receive()
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    break

            # Parse form data from body
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                parsed = parse_qs(body.decode("utf-8", errors="replace"))
                token_values = parsed.get(CSRF_FORM_FIELD, [])
                submitted_token = token_values[0] if token_values else None
            elif "multipart/form-data" in content_type:
                # For multipart, extract the csrf_token field from the raw body
                submitted_token = _extract_multipart_field(body, content_type, CSRF_FORM_FIELD)

            if not submitted_token:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token not provided in form or header"},
                )
                await response(scope, receive, send)
                return

            if not secrets.compare_digest(cookie_token, submitted_token):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token mismatch"},
                )
                await response(scope, receive, send)
                return

            # Replay the body for downstream handlers
            body_sent = False

            async def replay_receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                # After body is sent, return disconnect
                return {"type": "http.disconnect"}

            await self.app(scope, replay_receive, send)
            return

        # Header-based CSRF (no body reading needed)
        if not secrets.compare_digest(cookie_token, submitted_token):
            response = JSONResponse(
                status_code=403,
                content={"detail": "CSRF token mismatch"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _extract_multipart_field(body: bytes, content_type: str, field_name: str) -> str | None:
    """Extract a simple field value from multipart form data."""
    # Get the boundary from content-type
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip('"')
            break

    if not boundary:
        return None

    boundary_bytes = f"--{boundary}".encode()
    parts = body.split(boundary_bytes)

    for part in parts:
        # Look for Content-Disposition with our field name
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue

        headers = part[:header_end].decode("utf-8", errors="replace")
        if f'name="{field_name}"' in headers and "filename=" not in headers:
            value = part[header_end + 4:]
            # Strip trailing boundary markers
            value = value.rstrip(b"\r\n-")
            return value.decode("utf-8", errors="replace").strip()

    return None
