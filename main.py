from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import our database models and routers
# We import Base so we can create tables (only for development)
from database import engine
from models import Base
from logging_config import setup_logging
import logging
logger = logging.getLogger(__name__)

# Import all our routers (each router handles one domain of the bank)
from routers import (
    users,
    accounts,
    transactions,
    transfers,
    user_transactions,
)
setup_logging()



# Lifespan event handler (runs when the app starts and stops)
# This is the modern, recommended way in FastAPI instead of @app.on_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Bank API starting up")
    yield
    logger.info("Bank API shutting down")


# Create the main FastAPI application
app = FastAPI(
    title="Bank Management System API",
    description="A secure and scalable banking API built with FastAPI",
    version="0.1.0",
    lifespan=lifespan,          # Enables startup/shutdown events
    docs_url="/docs",           # Swagger UI
    redoc_url="/redoc",         # ReDoc documentation
)
# Create all tables if they don't exist (development only)
# This runs automatically on every startup — safe for SQLite
from models import Base  # Ensure Base is imported
Base.metadata.create_all(bind=engine)


# ====================== SECURITY & CORS ======================
# Very important for any public API (especially banking)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                    # Change this to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====================== ROUTERS (Modular Endpoints) ======================
# Each router is prefixed with /api so all endpoints become /api/...
# This keeps the code clean and organized
app.include_router(users.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(transfers.router, prefix="/api")
app.include_router(user_transactions.router, prefix="/api")


# ====================== ROOT HEALTH CHECK ======================
# Simple endpoint to confirm the API is running
@app.get("/")
def read_root():
    """
    Health check endpoint.
    Anyone visiting the root URL will see this welcome message.
    """
    return {
        "message": "Welcome to Bank Management System API",
        "status": "online",
        "version": "0.1.0",
        "docs": "/docs"
    }