from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlencode

from mvsuabot.availability import Slot, parse_days, parse_slots
from mvsuabot.config import Settings
from mvsuabot.http_probe import ProbeResult, run_probe


class EqueueSessionError(RuntimeError):
    pass


class EqueueRequestError(RuntimeError):
    pass


class EqueueRateLimitError(EqueueRequestError):
    """HTTP 429 — server asked to slow down polling."""


def days_url(settings: Settings) -> str:
    query = urlencode(
        {
            "serviceId": settings.service_id,
            "departmentId": settings.department_id,
        }
    )
    return f"{settings.api_base_url}/equeue/days?{query}"


def slots_url(settings: Settings, date: str) -> str:
    query = urlencode(
        {
            "serviceId": settings.service_id,
            "departmentId": settings.department_id,
            "date": date,
        }
    )
    return f"{settings.api_base_url}/equeue/slots?{query}"


async def fetch_available_days_from_session(session: object, settings: Settings, *, data_dir: Path) -> list[str]:
    """Fetch day list using an authenticated Playwright browser context."""
    days_result = await _get_json_via_session(
        session,
        days_url(settings),
        data_dir / "latest_days_response.json",
    )
    return parse_days(days_result)


async def fetch_available_slots_from_session(session: object, settings: Settings, *, data_dir: Path) -> list[Slot]:
    """Fetch slots using an authenticated Playwright browser context."""
    days = await fetch_available_days_from_session(session, settings, data_dir=data_dir)

    slots: list[Slot] = []
    for index, day in enumerate(days):
        slots_result = await _get_json_via_session(
            session,
            slots_url(settings, f"{day}T00:00:00"),
            data_dir / f"latest_slots_{day}.json",
        )
        slots.extend(parse_slots(slots_result, date=day))
        if index + 1 < len(days):
            await asyncio.sleep(2)

    return slots


async def fetch_available_slots_for_day_from_session(
    session: object,
    settings: Settings,
    *,
    date: str,
    data_dir: Path,
) -> list[Slot]:
    """Fetch slots for a single day using an authenticated Playwright browser context."""
    slots_result = await _get_json_via_session(
        session,
        slots_url(settings, date),
        data_dir / f"latest_slots_{date[:10]}.json",
    )
    return parse_slots(slots_result, date=date[:10])


async def fetch_available_slots_for_day(
    settings: Settings,
    *,
    date: str,
    data_dir: Path,
) -> list[Slot]:
    """Fetch slots for a single day using direct HTTP probe."""
    slots_result = await _get_json(
        settings,
        slots_url(settings, date),
        data_dir / f"latest_slots_{date[:10]}.json",
    )
    return parse_slots(slots_result, date=date[:10])


# Backward compatibility alias for older monitor code.
fetch_all_slots_after_login = fetch_available_slots_from_session


async def _get_json_via_session(session: object, url: str, output_path: Path) -> object:
    payload = await session.fetch_json(url)  # type: ignore[attr-defined]
    if payload is None:
        payload = {"data": []}
    output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


async def fetch_available_days(settings: Settings, *, data_dir: Path) -> list[str]:
    days_result = await _get_json(settings, days_url(settings), data_dir / "latest_days_response.json")
    return parse_days(days_result)


async def fetch_available_slots(settings: Settings, *, data_dir: Path) -> list[Slot]:
    days = await fetch_available_days(settings, data_dir=data_dir)

    slots: list[Slot] = []
    for day in days:
        slots_result = await _get_json(
            settings,
            slots_url(settings, f"{day}T00:00:00"),
            data_dir / f"latest_slots_{day}.json",
        )
        slots.extend(parse_slots(slots_result, date=day))

    return slots


async def _get_json(settings: Settings, url: str, output_path: Path) -> object:
    result = await run_probe(
        method="GET",
        url=url,
        headers=settings.request_headers,
        body=None,
    )
    output_path.write_text(result.text, encoding="utf-8")
    _raise_for_status(result)

    if result.status_code == 204:
        return {"data": []}

    try:
        return json.loads(result.text)
    except json.JSONDecodeError as exc:
        snippet = result.text.strip().replace("\n", " ")[:300]
        raise EqueueRequestError(
            f"Сервер повернув не JSON для {url}. Початок відповіді: {snippet}"
        ) from exc


def _raise_for_status(result: ProbeResult) -> None:
    if result.status_code in {401, 403}:
        raise EqueueSessionError(
            f"Сесія входу більше не дійсна або доступ заборонено: HTTP {result.status_code}."
        )

    if result.status_code == 429:
        raise EqueueRateLimitError(
            "Сервер обмежив частоту запитів (HTTP 429). Спробуйте пізніше."
        )

    if result.status_code in {502, 503, 504}:
        raise EqueueRateLimitError(
            f"Сервер тимчасово недоступний (HTTP {result.status_code}). Чекаю перед новою спробою."
        )

    if result.status_code not in {200, 204}:
        raise EqueueRequestError(
            f"Запит перевірки повернув HTTP {result.status_code}."
        )
