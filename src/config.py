import os
import re
from typing import Optional, Pattern
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self) -> None:
        self.bot_token: str = os.getenv("BOT_TOKEN", "")
        self.chat_id: str = os.getenv("CHAT_ID", "")
        # Optional: timeout for network requests, etc.
        self.request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
        # Headless mode for Playwright (set to False for debugging)
        self.headless: bool = os.getenv("HEADLESS", "true").lower() == "true"
        # Slow motion for Playwright (in milliseconds) to see actions
        self.slow_mo: int = int(os.getenv("SLOW_MO", "0"))
        # Base URL for the HSC website
        self.base_url: str = os.getenv("BASE_URL", "https://eqn.hsc.gov.ua/")
        # Service and department IDs to select
        self.service_id: str = os.getenv("SERVICE_ID", "43")
        self.department_id: str = os.getenv("DEPARTMENT_ID", "43")
        # Polling interval for checking queue (in seconds)
        self.polling_interval: int = int(os.getenv("POLLING_INTERVAL", "5"))
        # Selectors for the workflow (adjust if the website changes)
        self.login_indicator: str = os.getenv(
            "LOGIN_INDICATOR", 'text="Особистий кабінет"'
        )  # Text of an element indicating login
        self.cabinet_indicator: str = os.getenv(
            "CABINET_INDICATOR", 'text="Особистий кабінет"'
        )  # Text indicating cabinet page (can be same as login indicator)
        self.service_selection_link: str = os.getenv(
            "SERVICE_SELECTION_LINK", 'text="Записатися на прийом"'
        )  # Link to service selection
        self.proceed_button: str = os.getenv(
            "PROCEED_BUTTON", 'button:has-text("Дальше")'
        )  # Button to proceed to service center selection
        self.service_center_indicator: str = os.getenv(
            "SERVICE_CENTER_INDICATOR", 'text="Оберіть центр обслуговування"'
        )  # Text indicating service center selection page
        # Ticket API pattern to intercept
        self.ticket_api_pattern_str: str = os.getenv(
            "TICKET_API_PATTERN", r"/api/v1/ticket"
        )
        # Compile the regex pattern for efficiency
        self.ticket_api_pattern: Pattern = re.compile(self.ticket_api_pattern_str)

    def validate(self) -> None:
        """Validate required settings."""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN is required in .env file")
        if not self.chat_id:
            raise ValueError("CHAT_ID is required in .env file")


# Global settings instance
settings = Settings()