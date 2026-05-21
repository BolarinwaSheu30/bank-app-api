from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from crud import authenticate_user
from core import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from database import get_db

# ────────────────────────────────────────────────────────────────
# Authentication Router
# ────────────────────────────────────────────────────────────────
# This router handles login and token issuance.
# No prefix here — endpoints are directly under /api (set in main.py)
# Tag "auth" groups it nicely in Swagger/OpenAPI docs
router = APIRouter(tags=["auth"])


# ────────────────────────────────────────────────────────────────
# LOGIN ENDPOINT
# ────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    summary="Authenticate user and return JWT access token",
    response_model=dict,
    responses={
        401: {"description": "Invalid username or password"}
    }
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Authenticate user with username/password and issue a JWT access token.
    
    How it works:
    1. Receives form data (username + password) via OAuth2PasswordRequestForm
    2. Verifies credentials using authenticate_user (from crud.py)
    3. If valid → creates a JWT token with user ID as subject
    4. Returns token for use in Authorization: Bearer <token> header
    
    Security & Banking context:
    - Uses standard OAuth2 Password Flow (form-based login)
    - Short-lived access token (60 minutes by default)
    - No refresh token yet — add later for better UX/security
    - Raises 401 on failure with WWW-Authenticate header (standard for Bearer auth)
    
    Returns:
        dict: {"access_token": "...", "token_type": "bearer"}
    """
    # Attempt to authenticate user (checks username + password hash)
    user = authenticate_user(db, form_data.username, form_data.password)

    if not user:
        # Standard 401 response for failed login
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},  # Tells client to use Bearer token
        )

    # Set token expiration (short-lived for security)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Create JWT token with user ID as subject ("sub" claim)
    # Never put sensitive data in token payload (e.g. no balance, password)
    access_token = create_access_token(
        data={"sub": str(user.id)},  # Subject = user ID (cast to string)
        expires_delta=access_token_expires
    )

    # Return standard OAuth2 token response
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }