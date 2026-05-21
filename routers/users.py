from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from core import get_current_user
from models import User
from schemas import UserCreate, UserOut
from crud import create_user, get_user, get_user_by_username, authenticate_user
from core import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta

# ────────────────────────────────────────────────────────────────
# Users Router
# ────────────────────────────────────────────────────────────────
# Handles user registration, login, and basic user info retrieval.
# All routes are prefixed with /api (set in main.py)
# Tag "users" groups them in Swagger/OpenAPI docs
router = APIRouter(
    prefix="/users",
    tags=["users"],
    # dependencies=[Depends(get_current_user)]  # Optional: force auth on some/all routes
)


# ────────────────────────────────────────────────────────────────
# REGISTER NEW USER
# ────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account"
)
def register_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new user account (registration).
    
    Banking & Security context:
    - Username must be unique (checked in CRUD layer)
    - Password is hashed immediately using bcrypt
    - Returns safe UserOut schema (no password or hashed_password exposed)
    - No authentication required (public endpoint)
    
    Raises:
        400: Username already exists or invalid data
    
    Returns:
        UserOut: Newly created user details (id, username, full_name)
    """
    try:
        return create_user(db, user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ────────────────────────────────────────────────────────────────
# LOGIN / GET TOKEN
# ────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    summary="Login and get JWT access token"
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Authenticate user with username and password, return JWT access token.
    
    Banking & Security context:
    - Uses standard OAuth2 Password Flow (form-based login)
    - Verifies credentials against hashed password
    - Issues short-lived JWT token (60 minutes by default)
    - Token is used in Authorization: Bearer <token> for protected endpoints
    
    Raises:
        401: Incorrect username or password
    
    Returns:
        dict: {"access_token": "...", "token_type": "bearer"}
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create token with user ID as subject (sub claim)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


# ────────────────────────────────────────────────────────────────
# GET CURRENT USER PROFILE
# ────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current authenticated user's profile"
)
def read_users_me(
    current_user: User = Depends(get_current_user)
):
    """
    Return the profile of the currently authenticated user.
    
    Banking & Security context:
    - Protected endpoint: requires valid JWT token
    - Uses get_current_user dependency to validate token and fetch user
    - Returns safe UserOut schema (no password or sensitive data)
    - Useful for user dashboard / profile page
    
    Returns:
        UserOut: Current user's details (id, username, full_name)
    """
    return current_user