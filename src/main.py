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
    # Extract relevant information with fallbacks
    service_id = queue_data.get("service_id", queue_data.get("serviceId", "Unknown"))
    department_id = queue_data.get("department_id", queue_data.get("departmentId", "Unknown"))

    # Handle nested department data
    dept_info = queue_data.get("department", {})
    if isinstance(dept_info, dict):
        dept_name = dept_info.get("name", dept_info.get("title", "Unknown"))
        available_spots = dept_info.get("available", dept_info.get("available_spots", 0))
        total_spots = dept_info.get("total", dept_info.get("total_spots", 0))
    else:
        dept_name = "Unknown"
        available_spots = queue_data.get("available_spots", queue_data.get("available", 0))
        total_spots = queue_data.get("total_spots", queue_data.get("total", 0))

    # Try to get appointment availability or similar meaningful data
    available_days = queue_data.get("available_days", [])
    # Handle case where available_days might be a dict with a 'data' key
    if isinstance(available_days, dict) and 'data' in available_days:
        available_days = available_days.get('data', [])

    message_parts = [
        "🎟️ <b>Queue Update for MVS Bot</b>",
        f"Service ID: <b>{service_id}</b>",
        f"Department ID: <b>{department_id}</b>",
        f"Department: <b>{dept_name}</b>",
    ]

    if available_spots is not None:
        message_parts.append(f"Available Spots: <b>{available_spots}</b>")

    if total_spots is not None:
        message_parts.append(f"Total Spots: <b>{total_spots}</b>")

    if available_days:
        # Format the first few available dates (extract just date part from ISO timestamp)
        dates = []
        for day in available_days[:3]:  # Show first 3 dates
            if isinstance(day, dict) and 'date' in day:
                # Extract date part from ISO timestamp (YYYY-MM-DD)
                full_date = day['date']
                date_only = full_date.split('T')[0] if 'T' in full_date else full_date
                dates.append(date_only)
            else:
                dates.append(str(day))
        dates_str = ", ".join(dates)
        message_parts.append(f"Available Dates: <b>{dates_str}</b>")

    # Add a note about raw data availability (without using unsupported HTML tags)
    message_parts.append("\n<i>Raw data available in logs for debugging</i>")

    return "\n".join(message_parts)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user.")
        sys.exit(0)