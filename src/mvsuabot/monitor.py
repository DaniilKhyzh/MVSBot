from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path

from mvsuabot.availability import Slot, parse_days, parse_slots, summarize_slots
from mvsuabot.config import Settings, load_settings
from mvsuabot.equeue import (
    EqueueRateLimitError,
    EqueueSessionError,
    fetch_available_days,
    fetch_available_slots,
    fetch_available_days_from_session,
    fetch_available_slots_from_session,
    fetch_available_slots_for_day,
    fetch_available_slots_for_day_from_session,
)
from mvsuabot.notifier import notify
from mvsuabot.session_manager import BrowserClosedError, SessionExpiredError, SessionManager


DATA_DIR = Path("data")
LATEST_SLOTS_PATH = DATA_DIR / "latest_available_slots.txt"
LAST_SEEN_SLOTS_PATH = DATA_DIR / "last_seen_slots.json"
LAST_SEEN_DAYS_PATH = DATA_DIR / "last_seen_days.json"

MIN_RATE_LIMIT_WAIT_SECONDS = 120
START_RETRY_WAIT_SECONDS = 120
MONITOR_LOOP_INTERVAL_SECONDS = 13
SLOT_REFRESH_INTERVAL_SECONDS = 300

LAST_SLOT_FETCH_AT = 0.0
HAS_REPORTED_THIS_RUN = False

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Storage helpers
# ------------------------------------------------------------


def load_last_seen_slots(path: Path) -> list[Slot]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [
                Slot(
                    date=i["date"],
                    start_time=i["start_time"],
                    stop_time=i["stop_time"],
                )
                for i in data
                if isinstance(i, dict)
            ]
    except Exception as exc:
        logger.error(f"Помилка завантаження слотів: {exc}")
    return []


def save_last_seen_slots(path: Path, slots: list[Slot]) -> None:
    try:
        path.write_text(
            json.dumps([s.__dict__ for s in slots], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error(f"Помилка збереження слотів: {exc}")


def load_last_seen_days(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as exc:
        logger.error(f"Помилка завантаження днів: {exc}")
    return []


def save_last_seen_days(path: Path, days: list[str]) -> None:
    try:
        path.write_text(json.dumps(days, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.error(f"Помилка збереження днів: {exc}")


# ------------------------------------------------------------
# Notify helper
# ------------------------------------------------------------


async def _safe_notify(message: str, settings: Settings) -> None:
    try:
        await notify(
            message,
            telegram_bot_token=settings.telegram_bot_token,
            telegram_chat_id=settings.telegram_chat_id,
        )
    except Exception as exc:
        logger.error(f"Помилка сповіщення: {exc}")


# ------------------------------------------------------------
# API Check State
# ------------------------------------------------------------


class ApiCheckState:
    """State for the API checking process within a single session."""

    def __init__(self) -> None:
        self.cached_days: tuple[float, list[str]] | None = None
        self.days_cache_duration: float = 60.0  # Cache days for 60 seconds
        self.consecutive_429: int = 0  # Track consecutive 429 errors for backoff
        self.last_slot_fetch_at: float = 0.0  # Track last slot fetch for delay
        self.logger = logging.getLogger(__name__)


def _format_availability_summary(summary: str) -> str:
    if summary.startswith("Знайдено доступні слоти: "):
        payload = summary[len("Знайдено доступні слоти: "):]
        lines = [line.strip() for line in payload.split(";") if line.strip()]
        return "Знайдено доступні слоти:\n" + "\n".join(lines)
    return summary


def _short_availability_summary(slots: list[Slot]) -> str:
    if not slots:
        return "Доступних слотів не знайдено."

    dates = sorted({slot.date for slot in slots})
    total_slots = len(slots)
    if len(dates) <= 7:
        days_label = ", ".join(dates)
    else:
        days_label = ", ".join(dates[:7]) + f", +{len(dates) - 7} more"
    return f"Знайдено {total_slots} слотів у {len(dates)} днях: {days_label}."


# ------------------------------------------------------------
# Core check
# ------------------------------------------------------------


async def _check(settings: Settings, session: SessionManager | None = None, state: ApiCheckState | None = None) -> bool:
    """
    Check for available slots and notify if found.
    Returns True if slots were found, False otherwise.
    """
    if state is None:
        state = ApiCheckState()  # Temporary state for single call

    global LAST_SLOT_FETCH_AT, HAS_REPORTED_THIS_RUN

    first_check = not HAS_REPORTED_THIS_RUN
    previous_slots = load_last_seen_slots(LAST_SEEN_SLOTS_PATH)
    previous_days = load_last_seen_days(LAST_SEEN_DAYS_PATH)

    # Fetch or get cached days
    days = await _get_cached_days(settings, session, state)
    if not days:
        # No days available, wait and return
        await _handle_no_days(settings)
        return False

    total_days = len(days)
    num_batches = (total_days + 6) // 7
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await _safe_notify(
        f"[{timestamp}] 📅 Виявлено {total_days} днів. Починаю перевірку у {num_batches} пакетах.",
        settings,
    )

    # Check all available days in batches of 7 and wait between batches.
    MAX_DAYS_TO_CHECK = 7
    BATCH_WAIT_SECONDS = 27
    slots: list[Slot] = []
    batch_failed = False

    for batch_start in range(0, total_days, MAX_DAYS_TO_CHECK):
        batch_days = days[batch_start : batch_start + MAX_DAYS_TO_CHECK]
        batch_label = f"{batch_start + 1}-{batch_start + len(batch_days)}/{total_days}"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch_days_label = ", ".join(batch_days)
        state.logger.info(f"Checking days {batch_label}: {batch_days_label}")
        await _safe_notify(
            f"[{timestamp}] 🔎 Fetching days {batch_label}: {batch_days_label}",
            settings,
        )

        batch_slots: list[Slot] = []
        for i, day in enumerate(batch_days):
            # Add delay between slot requests (except for the first)
            if i > 0:
                delay = random.uniform(1.5, 3.5)
                await asyncio.sleep(delay)

            try:
                day_slots = await _fetch_slots_for_day(settings, session, day, state)
                slots.extend(day_slots)
                # Reset 429 counter on success
                state.consecutive_429 = 0

            except EqueueRateLimitError as exc:
                # Handle 429 with exponential backoff
                wait_time = _handle_429_error(state, exc)
                await asyncio.sleep(wait_time)
                batch_failed = True
                break
            except (SessionExpiredError, BrowserClosedError):
                raise
            except Exception as exc:
                # Handle other errors (including 504) with short delay
                wait_time = _handle_other_error(exc)
                await asyncio.sleep(wait_time)
                # Continue to next day if possible
                continue

            batch_slots.extend(day_slots)

        if batch_failed:
            break

        batch_slot_count = len(batch_slots)
        batch_summary = _short_availability_summary(batch_slots)
        await _safe_notify(
            f"[{timestamp}] ✅ Batch {batch_label} complete: fetched {len(batch_days)} days, {batch_slot_count} slots.\n{batch_summary}",
            settings,
        )

        if batch_start + MAX_DAYS_TO_CHECK < total_days:
            await asyncio.sleep(BATCH_WAIT_SECONDS)

    # If the loop was interrupted by a rate limit, do not save partial results.
    if batch_failed and state.consecutive_429 > 0:
        return False

    # Save state only after a complete pass through all available days.
    save_last_seen_days(LAST_SEEN_DAYS_PATH, days)
    save_last_seen_slots(LAST_SEEN_SLOTS_PATH, slots)

    availability = summarize_slots(slots)
    LATEST_SLOTS_PATH.write_text(availability.summary, encoding="utf-8")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slots_changed = set(previous_slots) != set(slots)
    state_changed = first_check or days != previous_days or slots_changed

    if state_changed:
        if availability.has_slots:
            short_summary = _short_availability_summary(slots)
            await _safe_notify(
                f"[{timestamp}] ✅ Знайдено доступні слоти. {short_summary}\nПеревірте кабінет вручну.",
                settings,
            )
            HAS_REPORTED_THIS_RUN = True
            return True
        elif not days:
            await _safe_notify(
                f"[{timestamp}] Перевірка активна: календар повернув data: [], доступних днів немає.",
                settings,
            )
        else:
            summary = _short_availability_summary(slots)
            await _safe_notify(
                f"[{timestamp}] 🔄 Зміна календаря: {summary}",
                settings,
            )
    else:
        state.logger.info(f"[{timestamp}] Без змін: {_short_availability_summary(slots)}")

    HAS_REPORTED_THIS_RUN = True
    return availability.has_slots


async def _get_cached_days(settings: Settings, session: SessionManager | None, state: ApiCheckState) -> list[str]:
    """Get days from cache or fetch if expired."""
    now = asyncio.get_event_loop().time()
    if state.cached_days and (now - state.cached_days[0]) < state.days_cache_duration:
        if state.cached_days[1]:
            return state.cached_days[1]
        # If cached days are empty, refresh every attempt instead of reusing stale empty results.

    # Reuse any days already fetched during session readiness.
    try:
        if session:
            ready_days = None
            if hasattr(session, "get_ready_days"):
                ready_days = session.get_ready_days()
            if ready_days:
                days = ready_days
            else:
                days = await fetch_available_days_from_session(session, settings, data_dir=DATA_DIR)
        else:
            days = await fetch_available_days(settings, data_dir=DATA_DIR)
        if days:
            state.cached_days = (now, days)
        else:
            state.cached_days = None
        state.logger.info(f"Fetched {len(days)} available days")
        return days
    except (SessionExpiredError, BrowserClosedError):
        raise
    except Exception as exc:
        state.logger.error(f"Failed to fetch days: {exc}")
        # Return cached days if available, even if expired
        if state.cached_days:
            return state.cached_days[1]
        return []


async def _fetch_slots_for_day(settings: Settings, session: SessionManager | None, day: str, state: ApiCheckState) -> list[Slot]:
    """Fetch slots for a specific day."""
    date_query = f"{day}T00:00:00"
    try:
        if session:
            slots = await fetch_available_slots_for_day_from_session(
                session,
                settings,
                date=date_query,
                data_dir=DATA_DIR,
            )
        else:
            slots = await fetch_available_slots_for_day(
                settings,
                date=date_query,
                data_dir=DATA_DIR,
            )
        state.logger.info(f"Fetched {len(slots)} slots for {day}")
        return slots
    except Exception:
        # Re-raise to be handled by _check
        raise


def _handle_429_error(state: ApiCheckState, exc: EqueueRateLimitError) -> float:
    """Handle 429 error with exponential backoff."""
    state.consecutive_429 += 1
    # Exponential backoff: 10 * 2^(n-1) seconds, max 120 seconds
    delay = min(10 * (2 ** (state.consecutive_429 - 1)), 120)
    state.logger.warning(f"API rate limit detected (429). Waiting {delay} seconds before retry. Consecutive 429s: {state.consecutive_429}")
    return delay


def _handle_other_error(exc: Exception) -> float:
    """Handle 504 and other errors with short delay."""
    logger = logging.getLogger(__name__)
    if isinstance(exc, EqueueRateLimitError) and "504" in str(exc):
        delay = random.uniform(5, 10)
        logger.warning(f"API gateway timeout (504). Retrying in {delay:.1f} seconds.")
        return delay
    else:
        # For other errors, use a short random delay
        delay = random.uniform(2, 5)
        logger.warning(f"API error: {type(exc).__name__}. Retrying in {delay:.1f} seconds.")
        return delay


async def _handle_no_days(settings: Settings) -> None:
    """Handle case when no days are available."""
    logger = logging.getLogger(__name__)
    logger.info("No available days found. Waiting before next check.")
    # No extra pause here; the outer monitor loop already sleeps between checks.


# ------------------------------------------------------------
# Main loop
# ------------------------------------------------------------


async def monitor_once() -> None:
    settings = load_settings()
    DATA_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger(__name__)

    session = SessionManager()
    try:
        await session.start(settings)
        # Create state for this single check
        state = ApiCheckState()
        state.logger = logger
        await _check(settings, session=session, state=state)
    finally:
        await session.close()


async def run_forever() -> None:
    settings = load_settings()
    DATA_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger(__name__)

    if settings.cookie_header:
        logger.info(
            "Cookie header ігнорується — використовується тільки браузерна сесія."
        )

    while True:
        session = SessionManager()
        try:
            try:
                await session.start(settings)
            except (SessionExpiredError, BrowserClosedError) as exc:
                msg = f"⚠️ Авторизація не завершилась: {exc}"
                logger.info(msg)
                await _safe_notify(msg, settings)
                await asyncio.sleep(START_RETRY_WAIT_SECONDS)
                continue
            except Exception as exc:
                msg = f"Не вдалося підготувати браузерну сесію: {exc}"
                logger.info(msg)
                await asyncio.sleep(START_RETRY_WAIT_SECONDS)
                continue

            # State for this session (inner loop)
            state = ApiCheckState()
            state.logger = logger

            # SINGLE CHECK LOCK (fix for double fetch / 429 bursts)
            check_lock = asyncio.Lock()

            while True:
                try:
                    async with check_lock:
                        await _check(settings, session=session, state=state)

                    await asyncio.sleep(MONITOR_LOOP_INTERVAL_SECONDS)

                except (SessionExpiredError, BrowserClosedError) as exc:
                    msg = f"⚠️ Сесія завершена: {exc}"
                    state.logger.info(msg)
                    await _safe_notify(msg, settings)
                    break

                except EqueueSessionError as exc:
                    msg = f"⚠️ API session error: {exc}"
                    state.logger.info(msg)
                    await _safe_notify(msg, settings)
                    break

                except Exception as exc:
                    state.logger.error(f"Помилка монітора: {exc}")
                    await asyncio.sleep(43)

        finally:
            await session.close()

        await asyncio.sleep(5)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_forever())


def main_once() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(monitor_once())


if __name__ == "__main__":
    main()