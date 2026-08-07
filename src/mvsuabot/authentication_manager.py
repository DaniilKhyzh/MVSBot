from __future__ import annotations

import asyncio
import logging
import re

from playwright.async_api import Page

from mvsuabot.config import Settings
from mvsuabot.notifier import notify


AUTH_COMPLETION_TIMEOUT_SECONDS = 45
OPTIONAL_CONTINUE_CLICK_TIMEOUT_MS = 3_000


class AuthenticationManager:
    """Handles the pre-authentication BankID/Monobank flow before monitor startup."""

    def __init__(self, page: Page, settings: Settings) -> None:
        self.page = page
        self.settings = settings
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def is_authentication_completed(url: str, body_text: str) -> bool:
        url_lower = url.lower()
        if "eqn.hsc.gov.ua" in url_lower and "/cabinet" in url_lower:
            text = body_text.lower()
            cabinet_markers = (
                "особистий кабінет",
                "мої записи",
                "записатись у чергу",
                "записатися у чергу",
                "практичний іспит",
                "сервісний центр",
            )
            login_markers = (
                "увійти",
                "bankid",
                "дія",
                "авторизац",
                "логін",
            )
            has_cabinet_content = any(marker in text for marker in cabinet_markers)
            has_login_prompt = any(marker in text for marker in login_markers)
            return has_cabinet_content and not has_login_prompt
        return False

    @staticmethod
    def is_bankid_callback(url: str) -> bool:
        return "id.gov.ua/bankid-auth-callback" in url.lower()

    @staticmethod
    def is_login_prompt(url: str, body_text: str) -> bool:
        url_lower = url.lower()
        if "eqn.hsc.gov.ua" not in url_lower:
            return False
        if "/cabinet" not in url_lower and "/queue" not in url_lower:
            return False
        text = body_text.lower()
        login_markers = (
            "увійти",
            "bankid",
            "дія",
            "авторизац",
            "логін",
        )
        return any(marker in text for marker in login_markers)

    @staticmethod
    def is_cabinet_page(url: str) -> bool:
        url_lower = url.lower()
        return "eqn.hsc.gov.ua" in url_lower and ("/cabinet" in url_lower or "/queue" in url_lower)

    @staticmethod
    def monobank_candidate_selectors() -> tuple[str, ...]:
        return (
            "a[aria-label='monobank']",
            "a[href*='monobank']",
            "a:has-text('monobank')",
            "div.bank-logo[title='monobank']",
            "h2.bank-name",
        )

    @staticmethod
    def bankid_candidate_urls() -> tuple[str, ...]:
        return (
            "https://id.gov.ua/bankid-nbu-auth",
        )

    @staticmethod
    def is_invalid_sidbi_error(url: str, body_text: str) -> bool:
        text = body_text.lower()
        url_lower = url.lower()
        return (
            "підмінено значення параметра sidbi" in text
            or "незвичайний запит" in text
            or "службова інформація" in text
        ) and ("id.bank.gov.ua" in url_lower or "id.gov.ua" in url_lower)

    @staticmethod
    def is_registration_button_visible(body_text: str) -> bool:
        """Check if the 'Записатись у чергу' button is visible on the page."""
        text = body_text.lower()
        return "записатись у чергу" in text

    async def run(self) -> bool:
        self.logger.info("Starting pre-authentication flow...")
        try:
            body_text = (await self.page.locator("body").inner_text())
            if self.is_authentication_completed(self.page.url, body_text):
                self.logger.info("Cabinet is already available. Skipping authentication flow.")
                return True
            if self.is_registration_button_visible(body_text):
                self.logger.info("'Записатись у чергу' button is visible. Authentication flow completed successfully.")
                return True

            await self._ensure_terms_accepted()
            await self._open_id_gov()
            await self._open_bankid()
            if self.is_invalid_sidbi_error(self.page.url, await self.page.locator("body").inner_text()):
                self.logger.warning("Detected invalid sidBi BankID error. Restarting auth flow from the service portal.")
                await self._ensure_terms_accepted()
                await self._open_id_gov()
                await self._open_bankid()
            await self._select_monobank()
            qr_url = await self._wait_for_qr_or_redirect(None)
            if qr_url:
                await self._notify_qr_url(qr_url)
                await asyncio.sleep(5)
                await self._click_continue_button_if_present()
                self.logger.info("QR link obtained. Waiting for the final auth redirect to complete.")
                auth_success = await self._wait_for_auth_completion(qr_url)
                if auth_success:
                    await self._finish_authentication()
                return auth_success

            self.logger.warning("QR link was not found on the page.")
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            from mvsuabot.session_manager import BrowserClosedError

            if isinstance(exc, BrowserClosedError):
                raise
            self.logger.exception("Pre-authentication flow failed: %s", exc)
            return False

    async def _looks_like_authenticated_cabinet(self) -> bool:
        url = self.page.url.lower()
        if "eqn.hsc.gov.ua" not in url:
            return False
        if "/cabinet" not in url and "/queue" not in url:
            return False

        body_text = (await self.page.locator("body").inner_text()).lower()
        cabinet_markers = (
            "особистий кабінет",
            "мої записи",
            "записатись у чергу",
            "записатися у чергу",
            "практичний іспит",
            "сервісний центр",
        )
        login_markers = (
            "увійти",
            "bankid",
            "дія",
            "авторизац",
            "логін",
        )

        has_cabinet_content = any(marker in body_text for marker in cabinet_markers)
        has_login_prompt = any(marker in body_text for marker in login_markers)
        return has_cabinet_content and not has_login_prompt

    async def _ensure_terms_accepted(self) -> None:
        self.logger.info("Opening service page...")
        try:
            body_text = await self.page.locator("body").inner_text()
            if self.is_authentication_completed(self.page.url, body_text) or self.is_registration_button_visible(body_text):
                self.logger.info("Cabinet or 'Записатись у чергу' is already ready. Skipping terms acceptance.")
                return
        except Exception:
            pass

        current_url = self.page.url.lower()
        if "eqn.hsc.gov.ua" not in current_url:
            try:
                await self.page.goto("https://eqn.hsc.gov.ua", wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                if "ERR_ABORTED" in str(exc) or "net::ERR_ABORTED" in str(exc):
                    self.logger.info("Page navigation aborted due to active redirect; waiting for load state.")
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    except Exception:
                        pass
                else:
                    raise
        else:
            self.logger.info("Already on MVS portal (%s).", self.page.url)

        try:
            await self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            self.logger.info("Service page is still loading; continuing with visible element waits.")

        checkbox_text = "Я ознайомлений та погоджуюсь з умовами надання послуги"
        checkbox = self.page.get_by_text(checkbox_text, exact=True)
        login_button = self.page.get_by_role("button").filter(has_text="id.gov.ua")

        try:
            await checkbox.first.wait_for(state="visible", timeout=60_000)
        except Exception:
            self.logger.info("Service terms text was not found; waiting for the login button directly.")

        if await checkbox.count() > 0:
            await self._accept_service_terms(checkbox, login_button)

        await self._wait_for_login_button_ready(login_button)

    async def _accept_service_terms(self, checkbox: object, login_button: object) -> None:
        self.logger.info("Accepting service terms...")
        input_checkbox = self.page.locator("input[type='checkbox']")

        for attempt in range(1, 5):
            if await self._login_button_is_ready(login_button):
                self.logger.info("Service terms already accepted.")
                return

            try:
                await checkbox.first.scroll_into_view_if_needed()
                await checkbox.first.click(timeout=5_000)
            except Exception as exc:
                self.logger.info("Terms text click attempt %s failed: %s", attempt, exc)

            await asyncio.sleep(1)
            if await self._login_button_is_ready(login_button):
                self.logger.info("Service terms accepted.")
                return

            try:
                if await input_checkbox.count() > 0:
                    await input_checkbox.first.check(force=True, timeout=5_000)
            except Exception as exc:
                self.logger.info("Checkbox input check attempt %s failed: %s", attempt, exc)

            await asyncio.sleep(1)

        self.logger.warning("Service terms were not confirmed as accepted; continuing to login button wait.")

    async def _login_button_is_ready(self, login_button: object) -> bool:
        try:
            if await login_button.count() == 0:
                return False
            candidate = login_button.first
            return await candidate.is_visible(timeout=500) and await candidate.is_enabled(timeout=500)
        except Exception:
            return False

    async def _wait_for_login_button_ready(self, login_button: object) -> None:
        self.logger.info("Waiting for ID.GOV.UA login button to be ready...")
        deadline = asyncio.get_running_loop().time() + 60
        while asyncio.get_running_loop().time() < deadline:
            if await self._login_button_is_ready(login_button):
                return
            await asyncio.sleep(1)

        await login_button.first.wait_for(state="visible", timeout=5_000)

    async def _open_id_gov(self) -> None:
        self.logger.info("Opening ID.GOV.UA...")
        login_button = self.page.get_by_role("button").filter(has_text="id.gov.ua")
        clicked = await self._click_visible_element(
            login_button.first,
            "ID.GOV.UA login button",
            expected_url_substrings=("id.gov.ua",),
        )
        if not clicked:
            self.logger.warning("The ID.GOV.UA login button was not confirmed as clicked.")
        await self.page.wait_for_url("**/id.gov.ua/**", timeout=60_000)

    async def _open_bankid(self) -> None:
        self.logger.info("Opening BankID...")
        current_url = self.page.url.lower()
        is_bankid_page = (
            "id.gov.ua/bankid" in current_url
            or "sidbi=" in current_url
        )
        if not is_bankid_page:
            for url in self.bankid_candidate_urls():
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    break
                except Exception as exc:
                    self.logger.info("BankID URL %s failed: %s", url, exc)
        else:
            self.logger.info("Already on a BankID page; keeping the current context.")

        await self.page.wait_for_load_state("domcontentloaded", timeout=30_000)

    @staticmethod
    def _looks_like_qr_url(value: str | None) -> bool:
        if not value:
            return False

        normalized = value.strip().lower()
        if not normalized:
            return False

        if not (
            normalized.startswith("http://")
            or normalized.startswith("https://")
            or normalized.startswith("monobank://")
        ):
            return False

        return (
            "api.monobank.ua" in normalized
            or ("monobank" in normalized and ("qr" in normalized or "bankid" in normalized))
            or normalized.startswith("monobank://")
        )

    @classmethod
    def _extract_qr_link_from_text(cls, text: str) -> str | None:
        matches = re.findall(r"(?:https?://|monobank://)[^\s'\"<>]+", text)
        for match in matches:
            candidate = match.rstrip(").,;]")
            if cls._looks_like_qr_url(candidate):
                return candidate
        return None

    async def _select_monobank(self) -> None:
        self.logger.info("Selecting Monobank...")

        continue_button = self.page.get_by_role("button", name="Продовжити")
        if await continue_button.count() > 0:
            self.logger.info("Clicking continue button to open the bank picker.")
            await self._click_visible_element(
                continue_button.first,
                "continue button",
                expected_url_substrings=("monobank", "id.gov.ua"),
            )

        await self.page.wait_for_load_state("domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        selectors = self.monobank_candidate_selectors()
        for selector in selectors:
            locator = self.page.locator(selector)
            for attempt in range(12):
                count = await locator.count()
                if count > 0:
                    for index in range(count):
                        candidate = locator.nth(index)
                        try:
                            if await candidate.is_visible(timeout=500):
                                clicked = await self._click_visible_element(
                                    candidate,
                                    f"Monobank selector: {selector}",
                                    expected_url_substrings=("monobank", "api.monobank.ua"),
                                )
                                if clicked:
                                    self.logger.info("Clicked Monobank selector: %s", selector)
                                    return
                        except Exception as exc:
                            self.logger.info("Monobank selector %s attempt %s failed: %s", selector, index + 1, exc)
                await asyncio.sleep(0.5)

        monobank_text = self.page.get_by_text("monobank", exact=False)
        for attempt in range(12):
            count = await monobank_text.count()
            if count > 0:
                for index in range(count):
                    candidate = monobank_text.nth(index)
                    try:
                        if await candidate.is_visible(timeout=500):
                            clicked = await self._click_visible_element(
                                candidate,
                                "Monobank text element",
                                expected_url_substrings=("monobank", "api.monobank.ua"),
                            )
                            if clicked:
                                self.logger.info("Clicked Monobank text element.")
                                return
                    except Exception as exc:
                        self.logger.info("Monobank text click attempt %s failed: %s", index + 1, exc)
            await asyncio.sleep(0.5)

        self.logger.warning("Monobank text link was not clicked.")

    async def _click_continue_button_if_present(self) -> bool:
        self.logger.info("Looking for the final continue button...")
        locators = (
            self.page.get_by_role("button", name="Продовжити"),
            self.page.get_by_text("Продовжити", exact=True),
            self.page.locator("button:has-text('Продовжити')"),
            self.page.locator("a:has-text('Продовжити')"),
        )
        for locator in locators:
            for attempt in range(4):
                try:
                    count = await locator.count()
                except Exception:
                    count = 0
                if count > 0:
                    for index in range(count):
                        candidate = locator.nth(index)
                        try:
                            clicked = await self._click_visible_element(
                                candidate,
                                "final continue button",
                                expected_url_substrings=("id.gov.ua", "monobank"),
                                visible_timeout_ms=OPTIONAL_CONTINUE_CLICK_TIMEOUT_MS,
                            )
                            if clicked:
                                self.logger.info("Clicked final continue button.")
                                return True
                        except Exception as exc:
                            self.logger.info("Continue button click attempt %s failed: %s", index + 1, exc)
                await asyncio.sleep(0.5)

        self.logger.info("Continue button was not found or could not be clicked.")
        return False

    async def _click_visible_element(
        self,
        locator: object,
        description: str,
        *,
        expected_url_substrings: tuple[str, ...] = (),
        expected_selector: str | None = None,
        visible_timeout_ms: int = 60_000,
    ) -> bool:
        try:
            await locator.wait_for(state="visible", timeout=visible_timeout_ms)
        except Exception as exc:
            self.logger.info("Element %s was not visible: %s", description, exc)
            return False

        before_url = self.page.url.lower()
        before_body_text = (await self.page.locator("body").inner_text()).strip()

        try:
            await locator.scroll_into_view_if_needed()
            await locator.click(timeout=0)
        except Exception as exc:
            self.logger.info("Click on %s failed: %s", description, exc)
            return False

        await self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
        await asyncio.sleep(1)

        after_url = self.page.url.lower()
        after_body_text = (await self.page.locator("body").inner_text()).strip()

        if expected_url_substrings and any(fragment in after_url for fragment in expected_url_substrings):
            return True

        if after_url != before_url:
            return True

        if after_body_text and after_body_text != before_body_text:
            return True

        try:
            if not await locator.is_visible(timeout=500):
                return True
        except Exception:
            pass

        self.logger.warning("Click on %s did not produce a visible page change.", description)
        return False

    async def _extract_qr_url(self) -> str | None:
        self.logger.info("Extracting QR authorization link...")

        qr_elements = self.page.locator("#qrcode")
        count = await qr_elements.count()
        for index in range(count):
            candidate = qr_elements.nth(index)
            for attribute in ("title", "href", "data-url", "src"):
                value = await candidate.get_attribute(attribute)
                if self._looks_like_qr_url(value):
                    self.logger.info("QR link extracted from %s.", attribute)
                    return value

            text = (await candidate.inner_text()).strip()
            text_qr_url = self._extract_qr_link_from_text(text)
            if text_qr_url:
                self.logger.info("QR link extracted from element text.")
                return text_qr_url

        for selector in (
            "a[href*='monobank']",
            "a[href*='api.monobank.ua']",
            "a[href*='qr']",
            "img[src*='qr']",
            "img[alt*='qr']",
            "img[title*='qr']",
        ):
            elements = self.page.locator(selector)
            count = await elements.count()
            for index in range(count):
                candidate = elements.nth(index)
                for attribute in ("href", "src", "title", "data-url"):
                    value = await candidate.get_attribute(attribute)
                    if self._looks_like_qr_url(value):
                        self.logger.info("QR link extracted from selector %s.", selector)
                        return value

                text = (await candidate.inner_text()).strip()
                text_qr_url = self._extract_qr_link_from_text(text)
                if text_qr_url:
                    self.logger.info("QR link extracted from selector text %s.", selector)
                    return text_qr_url

        try:
            body_text = (await self.page.locator("body").inner_text()).strip()
        except Exception:
            body_text = ""
        body_qr_url = self._extract_qr_link_from_text(body_text)
        if body_qr_url:
            self.logger.info("QR link extracted from body text.")
            return body_qr_url

        body_html = ""
        try:
            body_html = (await self.page.content()).strip()
        except Exception as exc:
            self.logger.info("Could not read page HTML for QR extraction: %s", exc)

        current_url = (self.page.url or "").strip()
        scanned_text = "\n".join(part for part in (body_text, body_html, current_url) if part)
        if self._looks_like_qr_url(current_url):
            self.logger.info("QR link extracted from page URL.")
            return current_url

        scanned_qr_url = self._extract_qr_link_from_text(scanned_text)
        if scanned_qr_url:
            self.logger.info("QR link extracted from regex match.")
            return scanned_qr_url

        return None

    async def _wait_for_qr_or_redirect(self, qr_url: str | None) -> str | None:
        self.logger.info("Waiting for the QR link or Monobank redirect...")
        await asyncio.sleep(2)
        deadline = asyncio.get_running_loop().time() + 90
        last_continue_click_at = 0.0
        while asyncio.get_running_loop().time() < deadline:
            if self.page.is_closed():
                from mvsuabot.session_manager import BrowserClosedError

                raise BrowserClosedError("Browser window closed during authentication")

            extracted = await self._extract_qr_url()
            if extracted:
                return extracted

            current_url = self.page.url.lower()
            if "id.gov.ua" in current_url and "monobank" not in current_url:
                now = asyncio.get_running_loop().time()
                if now - last_continue_click_at >= 5:
                    if await self._click_continue_button_if_present():
                        last_continue_click_at = now
                        await asyncio.sleep(2)
                        continue
                    last_continue_click_at = now

            if "monobank" in current_url:
                await asyncio.sleep(2)
                continue

            await asyncio.sleep(1)

        return await self._extract_qr_url()

    async def _notify_qr_url(self, qr_url: str) -> None:
        message = (
            "Monobank authorization required.\n\n"
            f"Open this link on your phone:\n{qr_url}\n\n"
            "Waiting for confirmation..."
        )
        self.logger.info("Telegram notification sent.")
        await notify(
            message,
            telegram_bot_token=self.settings.telegram_bot_token,
            telegram_chat_id=self.settings.telegram_chat_id,
        )

    async def _wait_for_auth_completion(self, qr_url: str | None) -> bool:
        self.logger.info("Waiting for the final authentication redirect to complete...")
        deadline = asyncio.get_running_loop().time() + AUTH_COMPLETION_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            if self.page.is_closed():
                from mvsuabot.session_manager import BrowserClosedError

                raise BrowserClosedError("Browser window closed during authentication")

            try:
                body_text = (await self.page.locator("body").inner_text()).strip()
            except Exception:
                body_text = ""

            current_url = self.page.url.lower()
            if self.is_authentication_completed(current_url, body_text) or self.is_registration_button_visible(body_text):
                self.logger.info("Authentication completed successfully: Cabinet / 'Записатись у чергу' detected.")
                return True

            if self.is_invalid_sidbi_error(current_url, body_text):
                self.logger.warning("Authentication flow hit an invalid sidBi error; waiting for manual recovery.")
                break

            if "id.gov.ua" in current_url and "monobank" not in current_url:
                if self.is_bankid_callback(current_url):
                    self.logger.info("BankID callback page detected; clicking final continue button.")
                clicked = await self._click_continue_button_if_present()
                if clicked:
                    try:
                        await self.page.wait_for_url(lambda u: "eqn.hsc.gov.ua" in u.lower(), timeout=15_000)
                    except Exception:
                        pass

            await asyncio.sleep(2)

        try:
            body_text = (await self.page.locator("body").inner_text()).strip()
            current_url = self.page.url.lower()
            if self.is_authentication_completed(current_url, body_text) or self.is_registration_button_visible(body_text):
                self.logger.info("Authentication completed successfully on final check.")
                return True
        except Exception:
            pass

        self.logger.warning(
            "Authentication redirect did not complete in %s seconds. Pre-auth will restart from the service portal.",
            AUTH_COMPLETION_TIMEOUT_SECONDS,
        )
        return False

    async def _finish_authentication(self) -> None:
        self.logger.info("Finishing authentication...")
        try:
            body_text = (await self.page.locator("body").inner_text()).strip()
        except Exception:
            body_text = ""
        current_url = self.page.url.lower()
        if not self.is_authentication_completed(current_url, body_text) and not self.is_registration_button_visible(body_text):
            self.logger.error("Authentication not completed after QR flow.")
            raise RuntimeError("Authentication failed to complete")
        self.logger.info("Authentication verified successfully.")
