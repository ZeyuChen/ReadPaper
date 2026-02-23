"""
Simple in-memory sliding-window rate limiter.

Designed for per-user request throttling on the /translate endpoint.
Not suitable for multi-instance deployments without external state (Redis).
For Cloud Run single-instance, this is sufficient.
"""

import time
from collections import defaultdict
from typing import Tuple

from fastapi import HTTPException, Request, Depends
from ..services.auth import get_current_user


class RateLimiter:
    """Sliding-window rate limiter with per-user tracking."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # user_id -> list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, user_id: str) -> Tuple[bool, int]:
        """
        Check if the user is within rate limits.
        
        Returns:
            (allowed, remaining) — whether the request is allowed and how many
            requests remain in the current window.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old entries
        timestamps = self._requests[user_id]
        self._requests[user_id] = [t for t in timestamps if t > cutoff]
        timestamps = self._requests[user_id]

        remaining = self.max_requests - len(timestamps)

        if len(timestamps) >= self.max_requests:
            return False, 0

        # Record this request
        timestamps.append(now)
        return True, remaining - 1


# Global rate limiter instance for translation requests
# 5 translations per minute per user
translate_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)


def check_translate_rate_limit(
    user_id: str = Depends(get_current_user),
) -> str:
    """
    FastAPI dependency that enforces rate limiting on translation requests.
    Returns user_id if within limits, raises 429 if exceeded.
    """
    allowed, remaining = translate_rate_limiter.check(user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded. You can submit up to "
                f"{translate_rate_limiter.max_requests} translations per minute. "
                f"Please wait and try again."
            ),
        )
    return user_id
