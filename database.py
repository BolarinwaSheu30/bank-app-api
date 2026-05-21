import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ====================== DATABASE CONFIGURATION ======================
# We use environment variables so we can easily switch between:
#   - SQLite (for local development)
#   - PostgreSQL (for production — strongly recommended for banking)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./bank.db"
)

# Render may provide postgres://
# SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

# SQLite needs this argument to work with FastAPI's multiple threads
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}


# Create the SQLAlchemy engine (the core connection to the database)
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    # These settings become very important when we switch to PostgreSQL:
    # pool_size=20,
    # max_overflow=10,
    # pool_pre_ping=True,
)


# Create a session factory
# autocommit=False and autoflush=False give us full control over transactions
# (critical for banking operations like transfers)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# Base class that all our models (User, Account, Transaction, etc.) will inherit from
Base = declarative_base()


# ====================== DATABASE DEPENDENCY ======================
# This function is used in every endpoint via Depends(get_db)
# It ensures every request gets its own database session and always closes it
def get_db():
    """
    Dependency that provides a database session to endpoints.
    FastAPI automatically calls this and injects 'db' into your route functions.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()          # Always close the session to prevent leaks