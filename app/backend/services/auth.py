"""
Auth service — authenticates requests via NextAuth JWT or header-based token.

When DISABLE_AUTH env var is set to 'true', all requests are treated as
'anonymous-user' (for local development and automated testing).

In production, the frontend (NextAuth) sets a session cookie. The backend
proxy forwards all cookies. We verify the user by:
1. Reading the 'x-user-email' header set by the frontend proxy, OR
2. Falling back to 'anonymous-user' if DISABLE_AUTH is true.

NOTE: For Cloud Run deployment, the frontend proxy reads the NextAuth session
and injects x-user-email header before forwarding to backend. This avoids
the backend needing to decode NextAuth JWTs directly (which requires the
same NEXTAUTH_SECRET and NextAuth internals).
"""

import os
from fastapi import Depends, HTTPException, Request

_DISABLE_AUTH = os.getenv("DISABLE_AUTH", os.getenv("NEXT_PUBLIC_DISABLE_AUTH", "false")).lower() == "true"


def get_current_user(request: Request = None) -> str:
    """
    Extract the current user ID (email) from the request.
    
    In production: reads x-user-email header forwarded by the frontend proxy.
    In dev mode (DISABLE_AUTH=true): returns 'anonymous-user'.
    """
    if _DISABLE_AUTH:
        return "anonymous-user"

    if request is None:
        return "anonymous-user"

    # The frontend proxy should inject x-user-email after verifying the session
    user_email = request.headers.get("x-user-email", "").strip()
    if user_email:
        return user_email

    # Fallback: check Authorization header (for direct API access)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        # In this simplified setup, the token IS the email
        # (set by the frontend proxy from the session)
        token = auth_header[7:].strip()
        if token and "@" in token:
            return token

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Please sign in."
    )
