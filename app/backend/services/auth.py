"""
Auth service — authentication DISABLED.

All authentication has been removed from this application.
Every request is treated as the fixed 'anonymous-user'.
This enables automated testing and local development without Google OAuth setup.
"""

def get_current_user() -> str:
    """Always returns the anonymous user — no token required."""
    return "anonymous-user"
