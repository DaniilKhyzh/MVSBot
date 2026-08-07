from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_MAX_LENGTH = 3800


def _split_message_into_chunks(message: str) -> list[str]:
    if len(message) <= TELEGRAM_MESSAGE_MAX_LENGTH:
        return [message]

    lines = message.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""

    for line in lines:
        if len(current) + len(line) <= TELEGRAM_MESSAGE_MAX_LENGTH:
            current += line
            continue

        if current:
            chunks.append(current)
            current = line
            continue

        # Single line is too long, split by character segments.
        for i in range(0, len(line), TELEGRAM_MESSAGE_MAX_LENGTH):
            chunks.append(line[i : i + TELEGRAM_MESSAGE_MAX_LENGTH])
        current = ""

    if current:
        chunks.append(current)

    return chunks


async def notify(
    message: str,
    *,
    telegram_bot_token: str | None,
    telegram_chat_id: str | None,
) -> None:
    if not telegram_bot_token or not telegram_chat_id:
        logger.warning("Telegram credentials missing; printing notification instead: %s", message)
        print(message, flush=True)
        return

    telegram_bot_token = telegram_bot_token.strip()
    telegram_chat_id = telegram_chat_id.strip()
    if not telegram_bot_token or not telegram_chat_id:
        logger.warning("Telegram credentials missing after stripping; printing notification instead: %s", message)
        print(message, flush=True)
        return

    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": telegram_chat_id,
        "disable_web_page_preview": True,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for chunk in _split_message_into_chunks(message):
            payload["text"] = chunk
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok", False):
                    logger.error("Telegram API error: %s", data.get("description", data))
                    print(
                        f"Telegram API error: {data.get('description', data)}",
                        flush=True,
                    )
            except httpx.HTTPError as exc:
                logger.exception("Failed to send Telegram message: %s", exc)
                print(
                    f"Не вдалося надіслати Telegram-повідомлення: {exc}",
                    flush=True,
                )
                break
            except Exception as exc:
                logger.exception("Unexpected error while sending Telegram message: %s", exc)
                print(
                    f"Помилка при відправці Telegram-повідомлення: {exc}",
                    flush=True,
                )
                break

