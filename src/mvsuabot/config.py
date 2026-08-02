from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


SET_COOKIE_ATTRS = frozenset({
    "path",
    "domain",
    "expires",
    "max-age",
    "secure",
    "httponly",
    "samesite",
    "priority",
})


def normalize_cookie_header(raw: str) -> str:
    """
    Convert a pasted browser cookie value into a valid Cookie request header.

    Accepts either a normal ``name=value; name=value`` string or a paste from
    DevTools Response ``Set-Cookie`` lines that includes ``Path=``, ``Domain=``, etc.
    """
    value = raw.strip()
    if not value:
        return value
    if "path=" not in value.lower() and "domain=" not in value.lower():
        return value

    parts: list[str] = []
    for chunk in value.split(";"):
        item = chunk.strip()
        if not item:
            continue
        lower = item.lower()
        name, _, _ = item.partition("=")
        if lower in SET_COOKIE_ATTRS or name.lower() in SET_COOKIE_ATTRS:
            continue
        if lower.startswith(("mon,", "tue,", "wed,", "thu,", "fri,", "sat,", "sun,")):
            continue
        if "=" in item:
            parts.append(item)
    return "; ".join(parts)


@dataclass(frozen=True)
class Settings:
    check_interval_seconds: int
    api_base_url: str
    service_id: int
    department_id: int
    request_method: str
    request_url: str
    request_headers: dict[str, str]
    request_body: str | None
    cookie_header: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    available_text_hint: str | None
    service_label: str | None
    department_label: str | None
    browser_channel: str | None
    browser_profile_dir: str
    auto_login_steps: bool

    def with_cookie(self, cookie: str) -> "Settings":
        """Return a new Settings instance with an updated Cookie header."""
        new_headers = {**self.request_headers, "Cookie": cookie}
        return dataclasses.replace(
            self,
            cookie_header=cookie,
            request_headers=new_headers,
        )


def load_settings() -> Settings:
    load_dotenv()

    headers_raw = os.getenv("MVS_REQUEST_HEADERS_JSON", "{}").strip() or "{}"
    try:
        headers = json.loads(headers_raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MVS_REQUEST_HEADERS_JSON must be valid JSON.") from exc

    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in headers.items()
    ):
        raise ValueError("MVS_REQUEST_HEADERS_JSON must be a JSON object with string values.")

    cookie_header = os.getenv("MVS_COOKIE_HEADER") or None
    if cookie_header:
        cookie_header = normalize_cookie_header(cookie_header)
        headers = {**headers, "Cookie": cookie_header}

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    auto_login_steps = os.getenv("MVS_AUTO_LOGIN_STEPS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return Settings(
        check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "60")),
        api_base_url=os.getenv("MVS_API_BASE_URL", "https://eqn.hsc.gov.ua/api/v2").strip().rstrip("/"),
        service_id=int(os.getenv("MVS_SERVICE_ID", "43")),
        department_id=int(os.getenv("MVS_DEPARTMENT_ID", "93")),
        request_method=os.getenv("MVS_REQUEST_METHOD", "GET").upper(),
        request_url=os.getenv("MVS_REQUEST_URL", "").strip(),
        request_headers=headers,
        request_body=os.getenv("MVS_REQUEST_BODY", "").strip() or None,
        cookie_header=cookie_header,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        available_text_hint=os.getenv("AVAILABLE_TEXT_HINT") or None,
        service_label=os.getenv("MVS_SERVICE_LABEL") or None,
        department_label=os.getenv("MVS_DEPARTMENT_LABEL") or None,
        browser_channel=os.getenv("MVS_BROWSER_CHANNEL", "chrome").strip() or None,
        browser_profile_dir=os.getenv("MVS_BROWSER_PROFILE_DIR", "data/browser-profile"),
        auto_login_steps=auto_login_steps,
    )
