import logging
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends messages to a Telegram chat via the Bot API."""

    def __init__(self) -> None:
        if not settings.bot_token or not settings.chat_id:
            raise ValueError("BOT_TOKEN and CHAT_ID must be set in the environment.")
        self.bot_token = settings.bot_token
        self.chat_id = settings.chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_message(self, text: str) -> None:
        """
        Send a text message to the configured chat.

        Args:
            text: The message text to send.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",  # Enable basic HTML formatting
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.api_url, json=payload, timeout=10.0)
                response.raise_for_status()
                logger.info("Telegram message sent successfully.")
            except httpx.RequestError as e:
                logger.error(f"Failed to send Telegram message: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Telegram API returned error {e.response.status_code}: {e.response.text}"
                )

    async def send_ticket_notification(self, ticket_info: dict) -> None:
        """
        Format and send a notification about the ticket.

        Args:
            ticket_info: Dictionary containing 'number' and optionally 'link'.
        """
        ticket_number = ticket_info.get("number", "Unknown")
        ticket_link = ticket_info.get("link", "")

        message = (
            f"🎟️ <b>Your queue ticket is ready!</b>\n"
            f"Ticket number: <b>{ticket_number}</b>\n"
        )
        if ticket_link:
            message += f"<a href='{ticket_link}'>Click here to view your ticket</a>"
        else:
            message += "No link provided."

        await self.send_message(message)