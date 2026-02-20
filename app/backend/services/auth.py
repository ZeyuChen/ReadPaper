
import os
from fastapi import HTTPException, Security, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests
from typing import Optional
from ..logging_config import setup_logger

logger = setup_logger("AuthService")

security = HTTPBearer(auto_error=False)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> str:
    """
    Verifies the Google ID Token or NextAuth JWT.
    """
    # Allow total bypass if configured (for local dev without dev tokens)
    if os.getenv("DISABLE_AUTH") == "true":
        return "local-dev-user"

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    
    # Dev Mode Bypass
    if token.startswith("DEV-TOKEN-"):
        # Allow simple bypass for local testing without Google Credentials
        # Format: DEV-TOKEN-user123
        return token.split("-", 2)[2]
        
    # Allow total bypass if configured (for local dev without dev tokens)
    if os.getenv("DISABLE_AUTH") == "true":
        return "local-dev-user"

    # Lazy load client ID to ensure env vars are loaded
    google_client_id = os.getenv("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID

    try:
        if not google_client_id:
             # If no client ID configured, and not a dev token, we can't verify properly.
             # But for now, let's log warning and maybe fail?
             # For now, if no Client ID, we might just fail safe.
             raise HTTPException(status_code=401, detail="Server not configured for authentication")
             
        id_info = id_token.verify_oauth2_token(token, requests.Request(), google_client_id)
        
        # Return the verified email (not sub/UID) so caller code can compare
        # against human-readable email strings like SUPER_ADMIN_EMAIL.
        email = id_info.get('email')
        if not email:
            raise HTTPException(status_code=401, detail="Token did not contain an email claim")
        return email
        
    except ValueError as e:
        logger.error(f"Token verification (ValueError) failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid authentication credentials: {e}")
    except Exception as e:
        logger.error(f"Token verification (General Exception) failed: {e}")
        logger.error(f"Token prefix received: {token[:20] if token else 'None'}...")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

