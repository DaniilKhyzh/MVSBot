"""
session_manager.py — Playwright session for MVS e-queue monitoring.

The bot opens Chrome and does NOT navigate or click during login.
The user completes BankID/Дія and the booking wizard manually.
API checks run via fetch() in the same tab (required for Akamai cookies).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from playwright.async_api import BrowserContext, Page, async_playwright

from mvsuabot.availability import parse_days
from mvsuabot.config import Settings
from mvsuabot.equeue import EqueueRateLimitError


EQUEUE_BASE = "https://eqn.hsc.gov.ua"
CABINET_URL = f"{EQUEUE_BASE}/cabinet"


class SessionExpiredError(RuntimeError):
    pass


class AuthActionError(RuntimeError):
    pass


class BrowserClosedError(RuntimeError):
    pass


# ------------------------------------------------------------
# Helpers (used by tests)
# ------------------------------------------------------------

def is_external_auth_url(url: str) -> bool:
    url_lower = url.lower()
    if "eqn.hsc.gov.ua" not in url_lower:
        return True
    auth_markers = (
        "bankid",
        "diia",
        "oauth",
        "auth",
        "login",
        "nidp",
        "privat",
        "monobank",
        "oschadbank",
        "oidc",
    )
    return any(marker in url_lower for marker in auth_markers)


def should_fetch_from_page(page_url: str) -> bool:
    if "eqn.hsc.gov.ua" not in page_url.lower():
        return False
    return not is_external_auth_url(page_url)


def page_looks_loaded(body_text: str) -> bool:
    text = body_text.strip().lower()
    if len(text) < 20:
        return False
    bad_markers = (
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway",
    )
    return not any(marker in text for marker in bad_markers)


def page_looks_like_login_prompt(body_text: str) -> bool:
    text = body_text.lower()
    login_markers = ("увійти", "bankid", "дія.підпис", "дія підпис", "авторизац")
    cabinet_markers = (
        "особистий кабінет",
        "записатись у чергу",
        "записатися у чергу",
        "мої записи",
    )
    return any(marker in text for marker in login_markers) and not any(
        marker in text for marker in cabinet_markers
    )


def page_looks_like_authenticated_cabinet(url: str, body_text: str) -> bool:
    url_lower = url.lower()
    text = body_text.lower()
    if "eqn.hsc.gov.ua" not in url_lower:
        return False
    if is_external_auth_url(url_lower):
        return False
    if not ("/cabinet" in url_lower or "/queue" in url_lower):
        return False
    if not page_looks_loaded(body_text):
        return False
    if page_looks_like_login_prompt(body_text):
        return False
    cabinet_markers = (
        "особистий кабінет",
        "записатись у чергу",
        "мої записи",
        "практичний іспит",
        "сервісний центр",
    )
    return any(marker in text for marker in cabinet_markers)


def page_shows_gateway_error(body_text: str) -> bool:
    text = body_text.lower()
    return (
        "502 bad gateway" in text
        or "503 service unavailable" in text
        or "504 gateway" in text
    )


def auth_page_kind(url: str) -> str:
    url_lower = url.lower()
    if "eqn.hsc.gov.ua" in url_lower:
        return "mvs_login"
    if "id.gov.ua/bankid-nbu-auth" in url_lower:
        return "bankid_bank_select"
    if "id.gov.ua/bankid-auth-callback" in url_lower:
        return "bankid_callback"
    if "id.gov.ua" in url_lower:
        return "id_gov_provider_select"
    return "external_manual_auth"


def days_url(settings: Settings) -> str:
    query = urlencode(
        {
            "serviceId": settings.service_id,
            "departmentId": settings.department_id,
        }
    )
    return f"{EQUEUE_BASE}/api/v2/equeue/days?{query}"


def build_fetch_options(url: str, settings: Settings | None) -> dict[str, object]:
    """Browser fetch options — uses page cookies only, never .env cookie header."""
    headers: dict[str, str] = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if settings is not None and settings.request_headers:
        for key, value in settings.request_headers.items():
            if key.lower() != "cookie" and value:
                headers[key] = value

    return {
        "method": "GET",
        "credentials": "include",
        "headers": headers,
    }


def api_status_is_ready(status: int) -> bool:
    return status in {200, 204}


def navigation_timeout_hint(url: str) -> str:
    return (
        f"Сайт повільно відкривається або не завершив завантаження: {url}. "
        "Бот не падає; перевірте вікно браузера або зачекайте."
    )


def gateway_error_hint() -> str:
    return (
        "Сайт МВС зараз повертає 502/503/504. "
        "Бот не буде клікати сторінку помилки — зачекайте або оновіть сторінку вручну."
    )


def calendar_setup_instructions(settings: Settings) -> str:
    service = settings.service_label or "практичний іспит"
    department = settings.department_label or f"сервісний центр ID {settings.department_id}"
    return (
        "Очікую ваш вхід. Бот НЕ перезавантажує і НЕ клікає сторінку.\n"
        "1. Увійдіть через BankID або Дія.Підпис\n"
        "2. Бот сам дійде до календаря і почне моніторити обраний ТСЦ МВС"
        "Бот продовжить, коли API календаря відповість."
    )


# ------------------------------------------------------------
# Session manager
# ------------------------------------------------------------

class SessionManager:
    def __init__(self) -> None:
        import logging
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ready = False
        self._settings: Settings | None = None
        self._fetch_lock = asyncio.Lock()
        self._gateway_error_reported = False
        self._ready_days: list[str] | None = None
        self.logger = logging.getLogger(__name__)

    async def start(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright = await async_playwright().start()

        profile_dir = Path(settings.browser_profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": False,
            "locale": "uk-UA",
            "viewport": {"width": 1280, "height": 800},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if settings.browser_channel:
            launch_kwargs["channel"] = settings.browser_channel

        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                **launch_kwargs
            )
        except Exception:
            launch_kwargs.pop("channel", None)
            self._context = await self._playwright.chromium.launch_persistent_context(
                **launch_kwargs
            )

        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        # Flag to track if full exam navigation has been performed
        self._exam_navigated = False
        self._monitor_start_delay_done = False

        self.logger.info(
            "\n" + "=" * 60 + "\n"
            "Відкриваю Chrome для авторизації.\n"
            "Бот не чіпає сторінку — увійдіть і пройдіть майстер запису вручну.\n"
            "Не закривайте це вікно під час моніторингу.\n"
            + "=" * 60,
        )

        page = self._page
        if page.url in ("about:blank", "") or "eqn.hsc.gov.ua" not in page.url:
            await self._open_cabinet_once()

        await self._wait_for_calendar_ready(settings)
        self._ready = True
        self.logger.info("Авторизація успішна. Починаю моніторинг.")

    async def ensure_api_ready(self, settings: Settings) -> None:
        if self._ready:
            return
        await self._wait_for_calendar_ready(settings)
        self._ready = True

    def get_ready_days(self) -> list[str] | None:
        return self._ready_days

    async def fetch_json(self, url: str) -> Any:
        status, text = await self._fetch(url)

        if status == 0:
            raise RuntimeError(
                "API недоступний з поточної сторінки. "
                "Переконайтесь, що ви на eqn.hsc.gov.ua і календар відкритий."
            )
        if status in {401, 403}:
            raise SessionExpiredError(f"Сесія недійсна або закінчилась (HTTP {status}).")
        if status == 429:
            raise EqueueRateLimitError("Сервер обмежив частоту запитів (HTTP 429).")
        if status in {502, 503, 504}:
            raise EqueueRateLimitError(f"Сервер тимчасово недоступний (HTTP {status}).")
        if not api_status_is_ready(status):
            raise RuntimeError(f"HTTP {status} для {url}")

        if not text.strip():
            return []
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Некоректний JSON для {url}.") from exc

    async def close(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._playwright = None

    async def _open_cabinet_once(self) -> None:
        page = self._page
        assert page is not None
        if page.is_closed():
            raise BrowserClosedError("Вікно браузера закрите.")

        try:
            await page.goto(CABINET_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            self.logger.info(navigation_timeout_hint(CABINET_URL))

    async def _wait_for_calendar_ready(self, settings: Settings) -> None:
        self.logger.info(calendar_setup_instructions(settings))

        poll_seconds = 8
        deadline = asyncio.get_event_loop().time() + 600

        while asyncio.get_event_loop().time() < deadline:
            page = self._page
            assert page is not None
            if page.is_closed():
                raise BrowserClosedError("Вікно браузера закрите.")

            # After login, perform the service selection sequence once
            if settings.auto_login_steps and not getattr(self, "_exam_navigated", False):
                try:
                    self.logger.info("Starting service selection flow...")

                    # Step 1: Click "Записатись у чергу" button
                    self.logger.info('Clicking "Записатись у чергу" button')
                    await page.wait_for_selector('text="Записатись у чергу"', state="visible", timeout=60000)
                    await page.click('text="Записатись у чергу"', timeout=0)

                    # Step 2: Wait for navigation to https://eqn.hsc.gov.ua/cabinet/queue
                    self.logger.info('Waiting for navigation to cabinet/queue page')
                    await page.wait_for_url('https://eqn.hsc.gov.ua/cabinet/queue', timeout=60000)
                    self.logger.info("Successfully navigated to cabinet/queue page")

                    # Step 3: Click "Практичний іспит"
                    self.logger.info('Clicking "Практичний іспит" button')
                    # Wait for the element to be visible and enabled
                    await page.wait_for_selector('text="Практичний іспит"', state="visible", timeout=60000)
                    await page.click('text="Практичний іспит"')

                    # Step 4: Click "Практичний іспит на транспортному засобі навчального закладу"
                    self.logger.info('Clicking "Практичний іспит на транспортному засобі навчального закладу" button')
                    # Wait for the element to be visible and enabled
                    await page.wait_for_selector('text="Практичний іспит на транспортному засобі навчального закладу"', state="visible", timeout=60000)
                    await page.click('text="Практичний іспит на транспортному засобі навчального закладу"')

                    # Step 5: Click confirmation button with text "Так"
                    self.logger.info('Clicking confirmation button "Так"')
                    # Wait for the element to be visible and enabled
                    await page.wait_for_selector('text="Так"', state="visible", timeout=60000)
                    await page.click('text="Так"')

                    # Step 6: Click "категорія В"
                    self.logger.info('Clicking "категорія В" button')
                    # Wait for the element to be visible and enabled
                    await page.wait_for_selector('text="категорія В"', state="visible", timeout=60000)
                    await page.click('text="категорія В"')

                    self.logger.info("Service selection flow completed successfully")
                    self._exam_navigated = True
                    if not self._monitor_start_delay_done:
                        self.logger.info("Затримка 13 секунд перед початком моніторингу, щоб уникнути 429 на старті.")
                        await asyncio.sleep(13)
                        self._monitor_start_delay_done = True
                except Exception as exc:
                    self.logger.error(f"Service selection flow failed: {exc}")

            try:
                body_text = await page.text_content("body") or ""

            except Exception:
                body_text = ""

            if page_shows_gateway_error(body_text):
                if not self._gateway_error_reported:
                    self.logger.info(gateway_error_hint())
                    self._gateway_error_reported = True
                await asyncio.sleep(30)
                continue

            if page_looks_like_authenticated_cabinet(page.url, body_text):
                return

            poll_seconds = min(poll_seconds + 10, 60)
            self.logger.info(f"Сторінка ще не готова. Чекаю {poll_seconds} с перед наступною перевіркою...")
            await asyncio.sleep(poll_seconds)

        raise SessionExpiredError(
            "Календар не став доступним за 10 хвилин.\n"
            "Переконайтесь, що ви дійшли до календаря для serviceId="
            f"{settings.service_id}, departmentId={settings.department_id}."
        )

    async def _fetch(self, url: str) -> tuple[int, str]:
        async with self._fetch_lock:
            page = self._page
            if page is None:
                raise RuntimeError("Session not started")

            if not should_fetch_from_page(page.url):
                return 0, ""

            payload = {
                "url": url,
                "options": build_fetch_options(url, self._settings),
            }

            try:
                result = await page.evaluate(
                    """async (payload) => {
                        try {
                            const { url, options } = payload;
                            const response = await fetch(url, options);
                            const text = await response.text();
                            return { ok: true, status: response.status, text };
                        } catch (error) {
                            return { ok: false, status: 0, text: '', error: String(error) };
                        }
                    }""",
                    payload,
                )
            except Exception:
                return 0, ""

            if result.get("ok"):
                return int(result["status"]), str(result["text"])
            return 0, ""


class ManagedSession:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.manager = SessionManager()

    async def __aenter__(self) -> SessionManager:
        await self.manager.start(self._settings)
        return self.manager

    async def __aexit__(self, *_: object) -> None:
        await self.manager.close()
