from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime
from logging_config import setup_logging

# Initialize logging when app starts
setup_logging()


# ────────────────────────────────────────────────────────────────
# IdempotencyKey
# ────────────────────────────────────────────────────────────────
# Purpose: Prevents duplicate processing of the same request
#          (very important in financial APIs to avoid double-charging, double-deposits, etc.)
#
# How it works:
# - Client sends a unique idempotency key (e.g. UUID) with sensitive requests
# - We store key + user_id + request hash + response
# - On duplicate request → return cached response instead of re-processing
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id = Column(Integer, primary_key=True, index=True)

    # Client-provided unique key (usually UUID or random string)
    key = Column(String, nullable=False)

    # Which user made this request (security: prevents cross-user replay)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Hash of the request payload (to detect if content changed even if key is same)
    request_hash = Column(String, nullable=False)

    # Cached successful response (JSON string) to return on duplicate requests
    response_body = Column(Text, nullable=True)

    # When this idempotency record was created
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to the User who owns this key
    user = relationship("User")

    # Ensure the same user cannot reuse the same key twice
    # (different users can use the same key — that's safe)
    __table_args__ = (
        UniqueConstraint("key", "user_id", name="uq_idempotency_key_user"),
    )


# ────────────────────────────────────────────────────────────────
# User
# ────────────────────────────────────────────────────────────────
# Represents a bank customer / account holder.
# In a real app this would have more fields (email, phone, KYC status, role, etc.)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Unique username — used for login
    username = Column(String, unique=True, index=True, nullable=False)

    # Full legal name — required for compliance / KYC
    full_name = Column(String, nullable=False)

    # Hashed password — NEVER store plain text!
    # In real apps: use bcrypt, argon2, or passlib to hash this
    hashed_password = Column(String, nullable=False)

    # One user can own multiple accounts (savings, current, etc.)
    accounts = relationship("Account", back_populates="owner")


# ────────────────────────────────────────────────────────────────
# Account
# ────────────────────────────────────────────────────────────────
# A single bank account belonging to one user.
# Important note: balance is currently Float — for learning it's okay,
# but in production you MUST use Numeric/Decimal to prevent rounding errors.
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)

    # Unique account number (usually auto-generated, e.g. 10-digit or IBAN format)
    account_number = Column(String, unique=True, index=True, nullable=False)

    # Account type — savings, current, fixed deposit, etc.
    account_type = Column(String, default="savings", nullable=False)

    # Current balance
    # WARNING: Float is unsafe for money (floating-point precision issues).
    # Production recommendation: use Numeric(precision=19, scale=4) or Decimal.
    balance = Column(Float, default=0.0, nullable=False)

    # Foreign key to the user who owns this account
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationship back to the owning User
    owner = relationship("User", back_populates="accounts")

    # All transactions linked to this account (deposits, withdrawals, transfers)
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")


# ────────────────────────────────────────────────────────────────
# Transaction
# ────────────────────────────────────────────────────────────────
# Records every movement of money on an account.
# Critical for audit trails, statements, fraud detection, and reconciliation.
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    # Amount moved
    # Positive = credit (deposit, transfer_in, interest)
    # Negative = debit (withdrawal, transfer_out, fee)
    # Again: Float is used here for simplicity — switch to Numeric in production!
    amount = Column(Float, nullable=False)

    # Type of movement
    # Current allowed: deposit, withdrawal
    # Future: transfer_in, transfer_out, fee, interest, reversal, etc.
    type = Column(String, nullable=False)

    # Optional description or reference
    # e.g. "Salary deposit", "ATM withdrawal", "Transfer to John Doe"
    reference = Column(String, index=True, nullable=True)

    # Which account this transaction affects
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False,index=True)

    # When the transaction was recorded
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship back to the affected Account
    account = relationship("Account", back_populates="transactions")

class AuditLog(Base):
    """
    AuditLog table tracks important system/user actions.

    Why this is important in banking:
    - Track who did what
    - Detect fraud or suspicious activity
    - Provide history for compliance/legal checks
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # ID of the user performing the action (nullable for system actions)
    user_id = Column(Integer, nullable=True)

    # What action was performed (e.g. "create_transaction")
    action = Column(String, nullable=False)

    # What entity was affected (e.g. "transaction", "account")
    entity = Column(String, nullable=False)

    # ID of the affected entity (e.g. transaction ID)
    entity_id = Column(Integer, nullable=True)

    # Status of the action ("success" or "failed")
    status = Column(String, nullable=False)

    # Optional message (e.g. "Insufficient funds")
    message = Column(String, nullable=True)

    # Timestamp of when action occurred
    created_at = Column(DateTime, default=datetime.utcnow)