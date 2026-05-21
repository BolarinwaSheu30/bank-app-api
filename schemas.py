from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum



class TransactionType(str, Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"

# ────────────────────────────────────────────────────────────────
# Common base class for all schemas in this project
# ────────────────────────────────────────────────────────────────
# We use this base to apply consistent configuration to every Pydantic model
class BankSchema(BaseModel):
    """
    Base schema shared by all models in the bank API.
    
    Configures Pydantic to:
    - Allow direct conversion from SQLAlchemy ORM objects
    - Control how data is serialized to JSON
    
    This avoids repeating the same config in every class.
    """
    model_config = ConfigDict(
        from_attributes=True,           # Enables .model_validate(obj) when obj is a SQLAlchemy model
        # json_encoders={float: str}    # Optional: serialize floats as strings (recommended when using Decimal)
    )


# ────────────────────────────────────────────────────────────────
# USER SCHEMAS
# ────────────────────────────────────────────────────────────────

class UserBase(BankSchema):
    """
    Fields that are common to all user-related schemas (create, read, update).
    """
    username: str = Field(..., min_length=3, max_length=50, description="Unique username for login")
    full_name: str = Field(..., min_length=2, max_length=100, description="User's full legal name")


class UserCreate(UserBase):
    """
    Schema used when a new user registers (POST /users).
    Includes the plain-text password which will be hashed on the server.
    """
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Plain-text password (will be hashed before saving)"
    )

    

class UserOut(UserBase):
    """
    Response schema for user data.
    Used when returning user information (never includes password).
    """
    id: int = Field(..., description="Unique identifier of the user")

    # Important: hashed_password is intentionally NOT included here
    # This prevents accidental exposure of sensitive data


# ────────────────────────────────────────────────────────────────
# ACCOUNT SCHEMAS
# ────────────────────────────────────────────────────────────────

class AccountBase(BankSchema):
    """
    Common fields shared by all account-related schemas.
    """
    account_type: str = Field(
        default="savings",
        description="Type of account: savings, current, fixed deposit, etc."
    )


class AccountCreate(AccountBase):
    """
    Schema used when creating a new account.
    Currently minimal — later we can add initial_balance, currency, etc.
    """
    pass


class Account(AccountBase):
    """
    Response schema for account details.
    Shows the current state of an account to the owner or admin.
    """
    id: int = Field(..., description="Unique account identifier")
    owner_id: int = Field(..., description="ID of the user who owns this account")
    balance: float = Field(..., description="Current account balance (float for now – should be Decimal in production)")


# ────────────────────────────────────────────────────────────────
# TRANSACTION SCHEMAS
# ────────────────────────────────────────────────────────────────

class TransactionBase(BankSchema):
    """
    Common fields for all transaction-related schemas.
    """
    amount: float = Field(..., description="Transaction amount (positive value)")
    type: TransactionType = Field(..., description="Transaction type ")


class TransactionCreate(TransactionBase):
    """
    Schema used when creating a new transaction (deposit or withdrawal).
    """
    account_id: int = Field(..., gt=0, description="ID of the account to credit or debit")

    





class Transaction(TransactionCreate):
    """
    Response schema when returning a single transaction.
    """
    id: int = Field(..., description="Unique transaction identifier")


class TransactionOut(TransactionBase):
    """
    Full transaction record – used for transaction history / statements.
    """
    id: int = Field(..., description="Unique transaction identifier")
    account_id: int = Field(..., description="ID of the account this transaction belongs to")
    reference: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional reference or description (e.g. 'Salary deposit', 'ATM withdrawal')"
    )
    created_at: datetime = Field(..., description="Exact time when the transaction was recorded")


# ────────────────────────────────────────────────────────────────
# TRANSFER SCHEMAS
# ────────────────────────────────────────────────────────────────

class TransferCreate(BankSchema):
    """
    Schema used when requesting a money transfer between two accounts.
    
    This is one of the most sensitive operations in the entire API.
    Must be protected with authentication, authorization, and atomicity.
    """
    from_account_id: int = Field(..., gt=0, description="ID of the source account (must belong to the authenticated user)")
    to_account_id: int = Field(..., gt=0, description="ID of the destination account")
    amount: float = Field(..., gt=0, description="Amount to transfer (positive value)")
    
    # Recommended future fields (add when ready):
    # reference: Optional[str] = Field(None, max_length=100, description="Transfer note")
    # idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate processing")

class TransactionList(BankSchema):
    """
    Paginated transaction response.
    
    Used for transaction history endpoints.
    Includes metadata for pagination + actual transaction data.
    """
    total: int = Field(..., description="Total number of transactions available")
    limit: int = Field(..., description="Number of records returned")
    offset: int = Field(..., description="Pagination offset")
    data: List[TransactionOut] = Field(..., description="List of transactions")