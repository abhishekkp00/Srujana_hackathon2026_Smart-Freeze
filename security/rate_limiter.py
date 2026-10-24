"""In-memory Sliding Window Rate Limiter for Smart-Freeze API.

Prevents Denial-of-Service (DoS) and brute-force enumeration attacks by
throttling excessive requests per client identity or IP address.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict, deque
from typing import Dict, Tuple, Optional
from fastapi import HTTPException, Request, status

from security.audit import SecurityAuditLogger
from security.models import AuditSeverity


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter."""

    _instance: Optional["SlidingWindowRateLimiter"] = None
    _lock = threading.Lock()

    def __init__(self):
        # Key: (client_id, route_group) -> deque of request timestamps
        self._history: Dict[Tuple[str, str], deque[float]] = defaultdict(deque)

    @classmethod
    def get_instance(cls) -> "SlidingWindowRateLimiter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def check_rate_limit(
        self,
        client_id: str,
        route_group: str = "general",
        max_requests: int = 180,
        window_seconds: int = 60,
        endpoint: str = "",
        method: str = "",
    ) -> None:
        """Enforce rate limit for a client within a sliding time window.
        
        Raises HTTP 429 if the request count exceeds max_requests within window_seconds.
        """
        now = time.time()
        cutoff = now - window_seconds
        key = (client_id, route_group)

        with self._lock:
            q = self._history[key]
            # Remove expired timestamps
            while q and q[0] < cutoff:
                q.popleft()

            if len(q) >= max_requests:
                audit = SecurityAuditLogger.get_instance()
                audit.log_event(
                    event_type="RATE_LIMIT_EXCEEDED",
                    endpoint=endpoint,
                    method=method,
                    severity=AuditSeverity.WARNING,
                    ip_address=client_id,
                    details={
                        "route_group": route_group,
                        "requests_count": len(q),
                        "max_allowed": max_requests,
                        "window_seconds": window_seconds,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: maximum {max_requests} requests per {window_seconds}s for group '{route_group}'.",
                    headers={"Retry-After": str(window_seconds)},
                )

            q.append(now)


def rate_limit(route_group: str = "general", max_requests: int = 180, window_seconds: int = 60):
    """FastAPI dependency factory to enforce rate limiting."""
    def dependency(request: Request):
        limiter = SlidingWindowRateLimiter.get_instance()
        client_ip = request.client.host if request.client else "127.0.0.1"
        limiter.check_rate_limit(
            client_id=client_ip,
            route_group=route_group,
            max_requests=max_requests,
            window_seconds=window_seconds,
            endpoint=request.url.path,
            method=request.method,
        )
    return dependency
