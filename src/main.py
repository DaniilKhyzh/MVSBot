import asyncio
import sys

from .browser import BrowserManager
from .config import settings
from .logger import logger
from .telegram import TelegramNotifier


async def main() -> None:
    """Main entry point of the application."""
    logger.info("Starting MVS Bot...")
    try:
        settings.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    notifier = TelegramNotifier()
    browser = BrowserManager()

    # Continuously monitor for queue updates
    while True:
        try:
            logger.info("Starting workflow...")
            queue_data = await browser.run_workflow()

            if queue_data:
                logger.info("Queue data obtained")

                # Format a meaningful message from the queue data
                message = format_queue_notification(queue_data)
                await notifier.send_message(message)
                logger.info("Notification sent. Continuing to monitor...")
            else:
                logger.info("No new queue data available")

            # Wait before next check (45 seconds as requested)
            logger.info(f"Waiting {settings.polling_interval} seconds until next check...")
            await asyncio.sleep(settings.polling_interval)

        except Exception as e:
            logger.error(f"An error occurred in the main loop: {e}")
            logger.info(f"Retrying in {settings.polling_interval} seconds...")
            await asyncio.sleep(settings.polling_interval)


def format_queue_notification(queue_data: dict) -> str:
    """
    Format a notification message from queue data.

    Args:
        queue_data: Dictionary containing queue information from the API

    Returns:
        Formatted message string for Telegram
    """
    # Extract available slots
    available_slots = queue_data.get("available_slots", [])

    if not available_slots:
        return "No available slots found."

    # Build the message in the required format
    message_parts = ["🟢 New available slots!\n"]

    for slot in available_slots:
        if isinstance(slot, dict):
            date = slot.get('date', 'Unknown')
            times = slot.get('times', [])

            if times and isinstance(times, list):
                # Format date (extract YYYY-MM-DD if it's a full timestamp)
                if 'T' in date:
                    date_only = date.split('T')[0]
                else:
                    date_only = date

                # Format times (extract HH:MM if they include seconds)
                formatted_times = []
                for time_str in times:
                    if ':' in time_str:
                        parts = time_str.split(':')
                        if len(parts) >= 2:
                            # Take only HH:MM
                            formatted_times.append(f"{parts[0]}:{parts[1]}")
                        else:
                            formatted_times.append(time_str)
                    else:
                        formatted_times.append(time_str)

                # Add to message
                message_parts.append(f"📅 {date_only}")
                for time in formatted_times:
                    message_parts.append(f"• {time}")
                message_parts.append("")  # Empty line between dates

    # Remove the last empty line if exists
    if message_parts[-1] == "":
        message_parts.pop()

    return "\n".join(message_parts)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user.")
        sys.exit(0)