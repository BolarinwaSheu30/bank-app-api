from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from database import get_db
from core import get_current_user
from models import User
from schemas import TransactionOut
from crud import get_transactions_for_user

# ────────────────────────────────────────────────────────────────
# User Transactions Router
# ────────────────────────────────────────────────────────────────
# Handles fetching transaction history across ALL accounts of the authenticated user.
# All routes are prefixed with /api/transactions (set in main.py)
# Tag "transactions" groups it with other transaction-related endpoints in Swagger/OpenAPI docs
router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    # dependencies=[Depends(get_current_user)]  # Optional: force auth on all routes
)


# ────────────────────────────────────────────────────────────────
# GET ALL TRANSACTIONS FOR USER (ACROSS ALL ACCOUNTS)
# ────────────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=List[TransactionOut],
    summary="Get transaction history across all accounts of the authenticated user"
)
def read_user_transactions(
    limit: int = 20,
    offset: int = 0,
    tx_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve a paginated list of all transactions across every account owned by the current user.
    
    Banking & Security context:
    - Only the authenticated user can see their own transactions
    - Aggregates history from all accounts (savings, current, etc.)
    - Supports filtering by type, date range, and pagination (prevents loading thousands of rows)
    - Returns safe TransactionOut schema (no internal or sensitive data exposed)
    - Critical for user statements, activity tracking, and financial overview
    
    Parameters:
        limit: Max number of transactions to return (default 20)
        offset: Pagination offset (skip this many records)
        tx_type: Optional filter (e.g. "deposit", "withdrawal", "transfer_out")
        start_date / end_date: Optional date range filter
    
    Returns:
        List[TransactionOut]: User's transactions (newest first)
    """
    return get_transactions_for_user(
        db=db,
        user_id=current_user.id,  # Automatically uses the logged-in user
        limit=limit,
        offset=offset,
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date
    )