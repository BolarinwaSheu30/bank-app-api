from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from schemas import Account, AccountCreate
from crud import create_account, get_account, get_accounts_by_owner
from database import get_db
from core import get_current_user
from models import User

# ────────────────────────────────────────────────────────────────
# Accounts Router
# ────────────────────────────────────────────────────────────────
# This router handles all account-related endpoints.
# All routes are prefixed with /api/accounts (set in main.py)
# Tags are used for grouping in Swagger/OpenAPI docs
router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    # dependencies=[Depends(get_current_user)]  # Optional: force auth on all routes
)


# ────────────────────────────────────────────────────────────────
# CREATE ACCOUNT
# ────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=Account,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bank account for the authenticated user"
)
def create_new_account(
    account: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new bank account owned by the currently authenticated user.
    
    Security & Banking context:
    - Only logged-in users can create accounts
    - Owner_id is automatically set to the current user (prevents hijacking)
    - Response uses AccountOut schema (safe fields only)
    
    Returns:
        Account: Newly created account details
    """
    # Delegate to CRUD layer for database operation
    return create_account(db, account, owner_id=current_user.id)


# ────────────────────────────────────────────────────────────────
# GET SINGLE ACCOUNT (OWNER ONLY)
# ────────────────────────────────────────────────────────────────
@router.get(
    "/{account_id}",
    response_model=Account,
    summary="Get details of a specific account (only if owned by user)"
)
def read_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve details of a specific account by ID.
    
    Security & Banking context:
    - Only the account owner can view it (owner_id check)
    - Prevents unauthorized access to other users' accounts
    - 404 if account doesn't exist
    - 403 if user is not the owner
    
    Returns:
        Account: Account details if authorized
    """
    account = get_account(db, account_id=account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    # Critical authorization check
    if account.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this account"
        )

    return account


# ────────────────────────────────────────────────────────────────
# LIST ALL USER ACCOUNTS
# ────────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=List[Account],
    summary="List all accounts belonging to the authenticated user"
)
def read_my_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a list of all bank accounts owned by the currently logged-in user.
    
    Banking context:
    - Users can have multiple accounts (savings, current, etc.)
    - Returns safe AccountOut schema (no sensitive internal data)
    - No pagination yet — fine for small user account counts
    
    Returns:
        List[Account]: All accounts owned by the user
    """
    return get_accounts_by_owner(db, owner_id=current_user.id)