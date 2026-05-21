from fastapi import HTTPException, status
from passlib.context import CryptContext
from passlib.exc import PasswordTruncateError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from datetime import datetime
import json, hashlib, random, logging

from models import AuditLog, User, Account, Transaction, IdempotencyKey
from schemas import UserCreate, AccountCreate, TransactionCreate, TransferCreate

# =========================================================
# LOGGER CONFIGURATION
# =========================================================
logger = logging.getLogger(__name__)

# =========================================================
# SECURITY CONFIG
# =========================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =========================================================
# HELPER FUNCTIONS (DEDUPLICATED & STANDARDIZED)
# =========================================================

def generate_account_number():
    """
    Generate a random 10-digit account number.
    NOTE: Should ideally be UNIQUE at DB level.
    """
    return str(random.randint(1000000000, 9999999999))


def generate_reference(prefix: str) -> str:
    """
    Generate a consistent transaction reference.
    FIXED: Removed duplicate definitions and inconsistent format.
    """
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"


def generate_request_hash(payload: dict) -> str:
    """
    Generate deterministic hash for idempotency.
    FIXED: Removed duplicate definition.
    """
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(payload_str.encode()).hexdigest()


# =========================================================
# USER OPERATIONS
# =========================================================

def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, user: UserCreate):
    """
    Create user with secure password hashing.
    """

    # Ensure username is unique
    if get_user_by_username(db, user.username):
        raise HTTPException(400, "Username already registered")

    # Enforce bcrypt max length (important security constraint)
    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(400, "Password too long")

    try:
        hashed_password = pwd_context.hash(user.password)
    except PasswordTruncateError:
        raise HTTPException(400, "Password exceeds bcrypt limit")
    except Exception:
        raise HTTPException(500, "Failed to hash password")

    db_user = User(
        username=user.username,
        full_name=user.full_name,
        hashed_password=hashed_password,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


# =========================================================
# ACCOUNT OPERATIONS
# =========================================================

def create_account(db: Session, account: AccountCreate, owner_id: int):
    db_account = Account(
        **account.dict(),
        owner_id=owner_id,
        account_number=generate_account_number(),
        balance=0.0,
    )

    db.add(db_account)
    db.commit()
    db.refresh(db_account)

    return db_account


def get_account(db: Session, account_id: int):
    return db.query(Account).filter(Account.id == account_id).first()


def get_accounts_by_owner(db: Session, owner_id: int):
    return db.query(Account).filter(Account.owner_id == owner_id).all()


# =========================================================
# IDEMPOTENCY
# =========================================================

def get_or_create_idempotency_key(
    db: Session,
    *,
    key: str,
    user_id: int,
    payload: dict
):
    """
    Prevent duplicate request execution.
    """

    request_hash = generate_request_hash(payload)

    existing = db.query(IdempotencyKey).filter(
        IdempotencyKey.key == key,
        IdempotencyKey.user_id == user_id,
    ).first()

    if existing:
        if existing.request_hash != request_hash:
            raise ValueError("Idempotency key reused with different payload")
        return existing, False

    record = IdempotencyKey(
        key=key,
        user_id=user_id,
        request_hash=request_hash,
    )

    db.add(record)
    db.flush()  # IMPORTANT: reserve record without commit

    return record, True


# =========================================================
# AUDIT LOG
# =========================================================

def create_audit_log(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity: str,
    status: str,
    message: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """
    Add audit log entry.
    NOTE: No commit here (controlled externally).
    """
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        status=status,
        message=message,
    ))


# =========================================================
# TRANSACTION (DEPOSIT / WITHDRAWAL)
# =========================================================

def create_transaction(
    db: Session,
    transaction: TransactionCreate,
    account_id: int,
    *,
    user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> Transaction:

    logger.info(f"START tx | user={user_id} | type={transaction.type} | amount={transaction.amount}")

    record = None

    # ---------- IDEMPOTENCY ----------
    if idempotency_key and user_id:
        # Use stable payload (prevents float/hash issues)
        payload = {
            "type": transaction.type,
            "amount": float(transaction.amount),
        }

        record, is_new = get_or_create_idempotency_key(
            db=db,
            key=idempotency_key,
            user_id=user_id,
            payload=payload,
        )

        if not is_new and record.response_body:
            cached = json.loads(record.response_body)

            existing = db.query(Transaction).filter(
                Transaction.id == cached["id"]
            ).first()

            # FIX: prevent returning None
            if not existing:
                raise HTTPException(500, "Stored transaction missing")

            return existing

    try:
        # Lock account row (prevents race conditions)
        account = db.query(Account).filter(
            Account.id == account_id
        ).with_for_update().first()

        if not account:
            raise ValueError("Account not found")

        # ---------- BUSINESS LOGIC ----------
        if transaction.type == "deposit":
            account.balance += transaction.amount
            ref = generate_reference("DEP")

        elif transaction.type == "withdrawal":
            if account.balance < transaction.amount:
                raise ValueError("Insufficient funds")
            account.balance -= transaction.amount
            ref = generate_reference("WDR")

        else:
            raise ValueError("Invalid transaction type")

        db_transaction = Transaction(
            amount=transaction.amount,
            type=transaction.type,
            account_id=account.id,
            reference=ref,
        )

        db.add(db_transaction)

        # CRITICAL FIX: ensure ID exists before using it
        db.flush()

        logger.info(f"SUCCESS tx | id={db_transaction.id}")

        # ---------- IDEMPOTENCY SAVE ----------
        if record:
            record.response_body = json.dumps({
                "id": db_transaction.id,
                "amount": float(db_transaction.amount),
                "type": db_transaction.type,
                "account_id": db_transaction.account_id,
            })

        # ---------- AUDIT ----------
        create_audit_log(
            db,
            user_id,
            "create_transaction",
            "transaction",
            "success",
            f"{transaction.type} {transaction.amount}",
            db_transaction.id
        )

        # SINGLE COMMIT → atomic operation
        db.commit()

        db.refresh(db_transaction)

        return db_transaction

    except ValueError as e:
        db.rollback()

        logger.warning(f"FAILED tx | {e}")

        create_audit_log(db, user_id, "create_transaction", "transaction", "failed", str(e))
        db.commit()

        raise HTTPException(400, str(e))

    except Exception as e:
        db.rollback()

        logger.error(f"ERROR tx | {e}")

        create_audit_log(db, user_id, "create_transaction", "transaction", "failed", "internal error")
        db.commit()

        raise HTTPException(500, "Internal server error")


# =========================================================
# TRANSACTION QUERIES
# =========================================================

def get_transactions_by_account(
    db: Session,
    account_id: int,
    limit: int = 20,
    offset: int = 0,
    tx_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    query = db.query(Transaction).filter(Transaction.account_id == account_id)

    if tx_type:
        query = query.filter(Transaction.type == tx_type)
    if start_date:
        query = query.filter(Transaction.created_at >= start_date)
    if end_date:
        query = query.filter(Transaction.created_at <= end_date)

    total = query.count()

    transactions = (
        query.order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": transactions
    }


def get_transactions_for_user(
    db: Session,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    tx_type: Optional[str] = None,
):
    query = db.query(Transaction).join(Account).filter(Account.owner_id == user_id)

    if tx_type:
        query = query.filter(Transaction.type == tx_type)

    return query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit).all()


# =========================================================
# TRANSFER
# =========================================================

def transfer_money(db: Session, transfer: TransferCreate):

    logger.info(f"START transfer | from={transfer.from_account_id} → to={transfer.to_account_id}")

    try:
        from_acc = db.query(Account).filter(
            Account.id == transfer.from_account_id
        ).with_for_update().first()

        to_acc = db.query(Account).filter(
            Account.id == transfer.to_account_id
        ).with_for_update().first()

        # FIX: removed unnecessary db.refresh()

        if not from_acc or not to_acc:
            raise ValueError("Account not found")

        if from_acc.id == to_acc.id:
            raise ValueError("Cannot transfer to same account")

        if transfer.amount <= 0:
            raise ValueError("Invalid amount")

        if from_acc.balance < transfer.amount:
            raise ValueError("Insufficient funds")

        from_acc.balance -= transfer.amount
        to_acc.balance += transfer.amount

        ref = generate_reference("TRF")

        db.add_all([
            Transaction(amount=transfer.amount, type="transfer_out", account_id=from_acc.id, reference=ref),
            Transaction(amount=transfer.amount, type="transfer_in", account_id=to_acc.id, reference=ref),
        ])

        # AUDIT
        create_audit_log(db, None, "transfer", "transaction", "success", f"{transfer.amount}", None)

        db.commit()

        logger.info("SUCCESS transfer")

        return {"message": "Transfer successful", "reference": ref}

    except ValueError as e:
        db.rollback()

        logger.warning(f"FAILED transfer | {e}")

        create_audit_log(db, None, "transfer", "transaction", "failed", str(e))
        db.commit()

        raise HTTPException(400, str(e))

    except Exception as e:
        db.rollback()

        logger.error(f"ERROR transfer | {e}")

        create_audit_log(db, None, "transfer", "transaction", "failed", "internal error")
        db.commit()

        raise HTTPException(500, "Internal server error")