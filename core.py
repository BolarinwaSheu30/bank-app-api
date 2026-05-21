from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from models import User
from database import get_db
import os


# ────────────────────────────────────────────────────────────────
# JWT (JSON Web Token) Configuration
# ────────────────────────────────────────────────────────────────
# These constants control how authentication tokens are created & verified.
# CRITICAL: Never hardcode SECRET_KEY in production code!
#          Use environment variables (.env file) or secret management (Render env vars, AWS Secrets, etc.)

SECRET_KEY = os.getenv("SECRET_KEY")
print("SECRET_KEY LOADED:", SECRET_KEY)

if not SECRET_KEY:
    raise ValueError("SECRET_KEY not found in .env file")

ALGORITHM = "HS256"  # Symmetric signing algorithm (HS256 is fine for most apps)
ACCESS_TOKEN_EXPIRE_MINUTES = 10080  #(7days for testing) How long tokens are valid — balance security vs usability

# Security scheme for Bearer tokens (used in Depends() below)
# This tells FastAPI/Swagger to expect Authorization: Bearer <token> in requests
security = HTTPBearer(auto_error=False)


# ────────────────────────────────────────────────────────────────
# Token Creation
# ────────────────────────────────────────────────────────────────
def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a signed JWT access token containing user data (usually username/user_id).
    
    This token is returned to the client after successful login.
    The client must include it in the Authorization header for protected endpoints.
    
    Banking context:
    - Short expiration (e.g. 15–60 min) + refresh tokens is standard
    - Never include sensitive data in payload (e.g. no password, balance)
    
    Args:
        data: Dict with claims (e.g. {"sub": username})
        expires_delta: Optional custom expiration (defaults to ACCESS_TOKEN_EXPIRE_MINUTES)
    
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()  # Avoid modifying the original dict

    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Add expiration claim to payload
    to_encode.update({"exp": expire})

    # Sign & encode the token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ────────────────────────────────────────────────────────────────
# Get Current User (Dependency)
# ────────────────────────────────────────────────────────────────
# This function is used in protected routes via Depends(get_current_user)
# It extracts the Bearer token, verifies it, and returns the authenticated User

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    
    print("STEP 1: dependecy triggered")
    """
    Dependency that authenticates a user using a JWT Bearer token.

    Authentication Flow:
    --------------------
    1. Extract JWT token from Authorization header
       (Authorization: Bearer <token>)
    2. Decode token using SECRET_KEY and ALGORITHM
    3. Extract user identifier from token payload ("sub" claim)
    4. Fetch user from database using that identifier
    5. Return authenticated user object

    Security Notes:
    - Any failure returns HTTP 401 (Unauthorized)
    - Prevents access to protected banking operations
    - Token signature + expiration are verified automatically

    Returns:
        User: authenticated database user
    """

    # --------------------------------------------------
    # STEP 1 — Extract raw token string
    # credentials.credentials contains only the JWT,
    # without the "Bearer " prefix.
    # --------------------------------------------------
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail = "Not authenticated",
            headers = {"WWW-Authenticate":"Bearer"},
        )
    token = credentials.credentials
    print("STEP2:", token)

    # Standard authentication error (reused everywhere)
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # --------------------------------------------------
        # STEP 2 — Decode and verify JWT
        # This automatically checks:
        #   ✔ signature validity
        #   ✔ expiration time (exp claim)
        # --------------------------------------------------
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("STEP 3:", payload)

        # --------------------------------------------------
        # STEP 3 — Extract user ID from token
        # In your system:
        #   "sub" stores the USER ID (not username)
        # --------------------------------------------------
        user_id = payload.get("sub")
        if user_id is None:
            print("FAILED: sub missing")
            # Token exists but missing required data
            raise credentials_exception
        user_id = int(user_id)

    except JWTError as e:
        print("JWT ERROR:", e)
        # Includes:
        # - expired token
        # - invalid signature
        # - malformed token
        raise credentials_exception

    # --------------------------------------------------
    # STEP 4 — Fetch user from database using ID
    # Convert to int because JWT stores values as strings
    # --------------------------------------------------
    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None:
        # Token valid but user no longer exists
        raise credentials_exception

    # --------------------------------------------------
    # STEP 5 — Return authenticated user
    # FastAPI injects this into protected routes
    # --------------------------------------------------
    print("SUCCESS AUTH")
    return user