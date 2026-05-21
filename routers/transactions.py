from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from database import get_db
from core import get_current_user
from models import User
from schemas import TransactionCreate, TransactionOut, TransactionList
from crud import (
    create_transaction,
    get_account,
    get_transactions_by_account,
)

# ────────────────────────────────────────────────────────────────
# Transactions Router
# ────────────────────────────────────────────────────────────────
# Handles deposit, withdrawal, and transaction history for accounts.
# All routes are prefixed with /api/accounts (set in main.py)
# Tag "transactions" groups them in Swagger/OpenAPI docs
router = APIRouter(
    prefix="/accounts",
    tags=["transactions"],
    # dependencies=[Depends(get_current_user)]  # Optional: force auth on all routes
)


# ────────────────────────────────────────────────────────────────
# CREATE TRANSACTION (DEPOSIT / WITHDRAWAL)
# ────────────────────────────────────────────────────────────────
@router.post(
    "/{account_id}/transactions",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a deposit or withdrawal on a specific account"
)
def create_new_transaction(
    account_id: int,
    transaction: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Perform a deposit or withdrawal on the specified account.
    
    Security & Banking context:
    - Only the account owner can create transactions
    - Prevents unauthorized access to other users' accounts
    - Checks sufficient balance for withdrawals
    - Supports idempotency (via crud layer) to prevent duplicate processing
    - Uses row-level locking in crud to prevent race conditions
    
    Raises:
        404: Account not found
        403: Not authorized (wrong owner)
        400: Insufficient balance or invalid data
    
    Returns:
        TransactionOut: Details of the created transaction
    """
    # Fetch account (will be locked in crud layer for safety)
    account = get_account(db, account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    # Critical authorization check
    if account.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform transactions on this account"
        )

    # Early balance check (extra safety layer before crud logic)
    if transaction.type == "withdrawal" and account.balance < transaction.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient balance"
        )

    # Delegate to CRUD layer (handles locking, idempotency, atomicity)
    return create_transaction(
        db=db,
        transaction=transaction,
        account_id=account.id,
        user_id=current_user.id,  # Passed for idempotency key association
    )


# ────────────────────────────────────────────────────────────────
# GET TRANSACTION HISTORY FOR ACCOUNT
# ────────────────────────────────────────────────────────────────
@router.get(
    "/{account_id}/transactions",
    response_model=TransactionList,
    summary="Get transaction history for a specific account"
)
def read_account_transactions(
    account_id: int,
    limit: int = Query(10, le=100),
    offset: int = Query(0),
    tx_type: Optional[str] = Query(None,alias="type"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve a paginated list of transactions for the specified account.
    
    Security & Banking context:
    - Only the account owner can view its transaction history
    - Supports filtering by type, date range, and pagination
    - Returns safe TransactionOut schema (no sensitive internal data)
    - Critical for user statements, audit trails, and fraud monitoring
    
    Raises:
        404: Account not found
        403: Not authorized (wrong owner)
    
    Returns:
        List[TransactionOut]: Transactions (newest first)
    """
    # Fetch account to check existence and ownership
    account = get_account(db, account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    # Critical authorization check
    if account.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view transactions for this account"
        )

    # Fetch filtered & paginated transactions
    return get_transactions_by_account(
        db=db,
        account_id=account_id,
        limit=limit,
        offset=offset,
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date
    )