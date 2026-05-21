from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
import json

from database import get_db
from core import get_current_user
from models import User
from schemas import TransferCreate
from crud import transfer_money, get_account, get_or_create_idempotency_key

# ────────────────────────────────────────────────────────────────
# Transfers Router
# ────────────────────────────────────────────────────────────────
# Handles money transfers between accounts.
# All routes are prefixed with /api/transfers (set in main.py)
# Tag "transfers" groups them in Swagger/OpenAPI docs
router = APIRouter(
    prefix="/transfers",
    tags=["transfers"],
    # dependencies=[Depends(get_current_user)]  # Optional: force auth on all routes
)


# ────────────────────────────────────────────────────────────────
# CREATE TRANSFER (MONEY MOVEMENT)
# ────────────────────────────────────────────────────────────────
@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Transfer money between two accounts (idempotent)"
)
def create_transfer(
    transfer: TransferCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Perform a secure, idempotent money transfer between two accounts.
    
    Banking & Security context:
    - Idempotency key (required header) prevents duplicate transfers if client retries
    - Only the owner of the source account can initiate the transfer
    - Uses row-level locking in crud layer to prevent race conditions
    - Atomic: either fully succeeds or fully rolls back
    - Caches successful response for idempotent retries
    
    Headers:
        Idempotency-Key: Unique string (e.g. UUID) sent by client
    
    Raises:
        400: Invalid data (same account, insufficient funds, negative amount)
        403: Not authorized to transfer from source account
        404: One or both accounts not found
        500: Unexpected server error
    
    Returns:
        dict: Transfer confirmation with amount, accounts, message
    """
    try:
        # ─── Step 1: Idempotency check & reservation ───
        # This happens BEFORE any money movement for safety
        # Prevents double-processing on network retry
        record, is_new = get_or_create_idempotency_key(
            db=db,
            key=idempotency_key,
            user_id=current_user.id,
            payload=transfer.dict()
        )

        # ─── Step 2: Return cached response if already processed ───
        # Fast path for safe retries — no re-processing needed
        if not is_new and record.response_body:
            return json.loads(record.response_body)

        # ─── Step 3: Fetch accounts ───
        # We fetch both accounts to validate existence & ownership
        from_account = get_account(db, transfer.from_account_id)
        to_account = get_account(db, transfer.to_account_id)

        if not from_account or not to_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or both accounts not found"
            )

        # Critical authorization: only source account owner can initiate
        if from_account.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not allowed to transfer from this account"
            )

        # ─── Step 4: Perform the actual transfer ───
        # This is delegated to CRUD layer which handles:
        # - Row-level locking (with_for_update)
        # - Balance checks & updates
        # - Creating two transaction records (out & in)
        # - Atomic commit/rollback
        response = transfer_money(db, transfer)

        # ─── Step 5: Cache successful response for idempotency ───
        # Ensures future requests with same key return same result
        record.response_body = json.dumps(response)
        db.commit()

        return response

    except ValueError as e:
        # Business validation errors (insufficient funds, same account, etc.)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        # Catch-all for unexpected errors (e.g. DB failure)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer failed: {str(e)}"
        )