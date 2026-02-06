"""
QuickServe Legal - Rate Limiting

Simple in-memory rate limiter using a sliding window counter per IP.
For production, replace with Redis-backed rate limiting.
"""

import time
from collections import defaultdict
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitStore:
    """In-memory sliding window rate limit store."""

    def __init__(self):
        # {key: [(timestamp, ...)] }
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if the key has exceeded the rate limit."""
        now = time.monotonic()
        cutoff = now - window_seconds

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

        if len(self._requests[key]) >= max_requests:
            return True

        # Record this request
        self._requests[key].append(now)
        return False

    def reset(self):
        """Reset all rate limits (useful for testing)."""
        self._requests.clear()


# Global rate limit store
rate_limit_store = RateLimitStore()

# Rate limit configuration: {path: (max_requests, window_seconds)}
RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "/login": (10, 60),          # 10 attempts per minute
    "/register": (10, 60),       # 10 registrations per minute
    "/pnsa/login": (10, 60),     # 10 attempts per minute
    "/download": (30, 60),       # 30 downloads per minute
}


class RateLimitMiddleware:
    """
    Rate limiting middleware.

    Checks POST requests against rate limit rules based on path and client IP.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        # Only rate-limit POST requests
        if request.method != "POST":
            await self.app(scope, receive, send)
            return

        path = request.url.path

        # Find matching rate limit rule
        rule = None
        for rule_path, limits in RATE_LIMIT_RULES.items():
            if path == rule_path or path.startswith(rule_path + "/"):
                rule = limits
                break

        if rule is None:
            await self.app(scope, receive, send)
            return

        max_requests, window_seconds = rule

        # Build rate limit key from IP + path
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"

        if rate_limit_store.is_rate_limited(key, max_requests, window_seconds):
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(window_seconds)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
