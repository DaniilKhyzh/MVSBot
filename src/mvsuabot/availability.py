from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Availability:
    has_slots: bool
    summary: str


@dataclass(frozen=True)
class Slot:
    date: str
    start_time: str
    stop_time: str


def parse_days(payload: Any) -> list[str]:
    dates = sorted(set(_collect_dates(payload)))
    return dates


def parse_slots(payload: Any, *, date: str) -> list[Slot]:
    items = _unwrap_list(payload)
    slots: list[Slot] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        start_time = item.get("startTime")
        stop_time = item.get("stopTime")
        if isinstance(start_time, str) and isinstance(stop_time, str):
            slots.append(Slot(date=date, start_time=start_time, stop_time=stop_time))

    return slots


def summarize_slots(slots: list[Slot]) -> Availability:
    if not slots:
        return Availability(False, "Доступних слотів не знайдено.")

    grouped: dict[str, list[Slot]] = {}
    for slot in slots:
        grouped.setdefault(slot.date, []).append(slot)

    parts = []
    for date, date_slots in sorted(grouped.items()):
        times = ", ".join(
            f"{slot.start_time}-{slot.stop_time}"
            for slot in sorted(date_slots, key=lambda value: value.start_time)
        )
        parts.append(f"{date}: {times}")

    return Availability(True, "Знайдено доступні слоти: " + "; ".join(parts) + ".")


def _collect_dates(value: Any) -> list[str]:
    dates: list[str] = []

    if isinstance(value, str):
        dates.extend(DATE_RE.findall(value))
        return dates

    if isinstance(value, list):
        for item in value:
            dates.extend(_collect_dates(item))
        return dates

    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and key.lower() in {"date", "day", "slotdate"}:
                dates.extend(DATE_RE.findall(item))
            else:
                dates.extend(_collect_dates(item))

    return dates


def _looks_like_empty_calendar(payload: Any) -> bool:
    if payload == []:
        return True

    if isinstance(payload, dict):
        for key in ("data", "days", "items", "result", "availableDays"):
            if payload.get(key) == []:
                return True

    return False


def _has_non_empty_calendar_like_data(payload: Any) -> bool:
    if isinstance(payload, list):
        return bool(payload)

    if isinstance(payload, dict):
        for key in ("data", "days", "items", "result", "availableDays"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                return True

    return False


def _unwrap_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("data", "days", "items", "result", "availableDays", "slots"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    return []
