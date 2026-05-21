import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Configure application-wide logging.

    Improvements over basicConfig:
    - Prevents duplicate logs
    - Adds file rotation (avoids huge log files)
    - Separates error logs
    """

    # -------------------------
    # CREATE FORMATTER
    # -------------------------
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s | %(message)s"
    )

    # -------------------------
    # CONSOLE HANDLER (terminal output)
    # -------------------------
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # -------------------------
    # FILE HANDLER (all logs)
    # -------------------------
    file_handler = RotatingFileHandler(
        "bank.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3              # keep last 3 files
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # -------------------------
    # ERROR FILE HANDLER (errors only)
    # -------------------------
    error_handler = RotatingFileHandler(
        "error.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # -------------------------
    # ROOT LOGGER
    # -------------------------
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Prevent duplicate logs if setup is called multiple times
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.addHandler(error_handler)