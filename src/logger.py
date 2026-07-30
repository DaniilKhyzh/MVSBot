import logging
import sys
from typing import Optional

from .config import settings


def setup_logger(name: str = "mv_sbot", log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up and return a logger with console and optional file output.

    Args:
        name: Logger name.
        log_file: Optional path to a log file. If None, only console logging is used.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent adding multiple handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Default logger instance
logger = setup_logger()