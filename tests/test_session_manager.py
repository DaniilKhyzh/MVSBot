import asyncio

from mvsuabot.authentication_manager import AuthenticationManager
from mvsuabot.config import Settings
from mvsuabot.session_manager import (
    api_status_is_ready,
    auth_page_kind,
    build_fetch_options,
    gateway_error_hint,
    is_external_auth_url,
    navigation_timeout_hint,
    page_looks_like_authenticated_cabinet,
    page_shows_gateway_error,
)


def test_is_external_auth_url_detects_bankid() -> None:
    assert is_external_auth_url("https://id.gov.ua/bankid/auth")
    assert is_external_auth_url("https://eqn.hsc.gov.ua/cabinet/login")
    assert not is_external_auth_url("https://eqn.hsc.gov.ua/cabinet")


def test_is_external_auth_url_detects_oauth() -> None:
    assert is_external_auth_url("https://oauth.example.com/authorize")
    assert is_external_auth_url("https://eqn.hsc.gov.ua/oidc/auth")


def test_build_fetch_options_includes_headers_and_credentials() -> None:
    settings = Settings(
        check_interval_seconds=60,
        api_base_url="https://eqn.hsc.gov.ua/api/v2",
        service_id=43,
        department_id=93,
        request_method="GET",
        request_url="",
        request_headers={"accept": "application/json"},
        request_body=None,
        cookie_header="should-not-be-used",
        telegram_bot_token=None,
        telegram_chat_id=None,
        available_text_hint=None,
        service_label=None,
        department_label=None,
        browser_channel=None,
        browser_profile_dir="data/browser-profile",
        auto_login_steps=False,
    )
    options = build_fetch_options("https://eqn.hsc.gov.ua/api/v2/equeue/days", settings)
    assert options["headers"]["accept"] == "application/json"
    assert "cookie" not in {k.lower() for k in options["headers"]}
    assert options["credentials"] == "include"


def test_api_status_ready_accepts_empty_calendar() -> None:
    assert api_status_is_ready(200)
    assert api_status_is_ready(204)
    assert not api_status_is_ready(401)
    assert not api_status_is_ready(429)


def test_authenticated_cabinet_requires_loaded_cabinet_content() -> None:
    assert page_looks_like_authenticated_cabinet(
        "https://eqn.hsc.gov.ua/cabinet",
        "Особистий кабінет. Записатись у чергу. Мої записи.",
    )
    assert not page_looks_like_authenticated_cabinet(
        "https://eqn.hsc.gov.ua/cabinet",
        "",
    )
    assert not page_looks_like_authenticated_cabinet(
        "https://eqn.hsc.gov.ua/cabinet/login",
        "Увійти через BankID або Дія.Підпис",
    )


def test_auth_page_kind() -> None:
    assert auth_page_kind("https://eqn.hsc.gov.ua/cabinet") == "mvs_login"
    assert auth_page_kind("https://id.gov.ua/?response_type=code") == "id_gov_provider_select"
    assert auth_page_kind("https://id.gov.ua/bankid-nbu-auth") == "bankid_bank_select"
    assert auth_page_kind("https://id.gov.ua/bankid-auth-callback?code=x") == "bankid_callback"
    assert auth_page_kind("https://api.monobank.ua/some-qr") == "external_manual_auth"


def test_navigation_timeout_hint_mentions_browser_wait() -> None:
    text = navigation_timeout_hint("https://eqn.hsc.gov.ua/cabinet")
    assert "не падає" in text
    assert "браузера" in text


def test_gateway_error_detection_and_hint() -> None:
    assert page_shows_gateway_error("<h1>502 Bad Gateway</h1>")
    assert page_shows_gateway_error("503 Service Unavailable")
    assert not page_shows_gateway_error("Особистий кабінет")
    assert "не буде клікати" in gateway_error_hint()


def test_authentication_flow_detects_completed_auth() -> None:
    assert not AuthenticationManager.is_authentication_completed(
        "https://id.gov.ua/bankid-auth-callback?code=test",
        "",
    )
    assert AuthenticationManager.is_bankid_callback(
        "https://id.gov.ua/bankid-auth-callback?code=test",
    )
    assert AuthenticationManager.is_authentication_completed(
        "https://eqn.hsc.gov.ua/cabinet",
        "Особистий кабінет. Мої записи.",
    )
    assert not AuthenticationManager.is_authentication_completed(
        "https://eqn.hsc.gov.ua/cabinet",
        "Увійти через BankID",
    )
    assert not AuthenticationManager.is_authentication_completed(
        "https://id.gov.ua/bankid-nbu-auth",
        "",
    )


def test_monobank_fallback_selectors_cover_bank_logo_markup() -> None:
    selectors = AuthenticationManager.monobank_candidate_selectors()
    assert "div.bank-logo[title='monobank']" in selectors
    assert "a[aria-label='monobank']" in selectors
    assert "h2.bank-name" in selectors


def test_extract_qr_url_reads_link_href_when_title_missing() -> None:
    class FakeElement:
        def __init__(self, attributes: dict[str, str]) -> None:
            self.attributes = attributes

        async def get_attribute(self, name: str) -> str | None:
            return self.attributes.get(name)

        async def inner_text(self) -> str:
            return ""

    class FakeLocator:
        def __init__(self, elements: list[FakeElement]) -> None:
            self.elements = elements

        async def count(self) -> int:
            return len(self.elements)

        def nth(self, index: int) -> FakeElement:
            return self.elements[index]

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://id.gov.ua/bankid"

        def locator(self, selector: str) -> FakeLocator:
            assert selector == "#qrcode"
            return FakeLocator([FakeElement({"href": "https://api.monobank.ua/qr?token=abc"})])

    manager = AuthenticationManager(page=FakePage(), settings=Settings(
        check_interval_seconds=60,
        api_base_url="https://eqn.hsc.gov.ua/api/v2",
        service_id=43,
        department_id=93,
        request_method="GET",
        request_url="",
        request_headers={},
        request_body=None,
        cookie_header="",
        telegram_bot_token=None,
        telegram_chat_id=None,
        available_text_hint=None,
        service_label=None,
        department_label=None,
        browser_channel=None,
        browser_profile_dir="data/browser-profile",
        auto_login_steps=False,
    ))

    qr_url = asyncio.run(manager._extract_qr_url())
    assert qr_url == "https://api.monobank.ua/qr?token=abc"


def test_extract_qr_url_falls_back_to_page_html_when_text_is_empty() -> None:
    class FakeElement:
        async def get_attribute(self, name: str) -> str | None:
            return None

        async def inner_text(self) -> str:
            return ""

    class FakeLocator:
        def __init__(self, elements: list[FakeElement] | None = None) -> None:
            self.elements = elements or []

        async def count(self) -> int:
            return len(self.elements)

        def nth(self, index: int) -> FakeElement:
            return self.elements[index]

        async def inner_text(self) -> str:
            return ""

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://id.gov.ua/bankid"
            self._html = '<script>window.__authUrl = "https://api.monobank.ua/qr?token=html";</script>'

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator([])

        async def content(self) -> str:
            return self._html

    manager = AuthenticationManager(page=FakePage(), settings=Settings(
        check_interval_seconds=60,
        api_base_url="https://eqn.hsc.gov.ua/api/v2",
        service_id=43,
        department_id=93,
        request_method="GET",
        request_url="",
        request_headers={},
        request_body=None,
        cookie_header="",
        telegram_bot_token=None,
        telegram_chat_id=None,
        available_text_hint=None,
        service_label=None,
        department_label=None,
        browser_channel=None,
        browser_profile_dir="data/browser-profile",
        auto_login_steps=False,
    ))

    qr_url = asyncio.run(manager._extract_qr_url())
    assert qr_url == "https://api.monobank.ua/qr?token=html"


def test_extract_qr_url_uses_page_url_when_it_is_the_auth_link() -> None:
    class FakeLocator:
        async def count(self) -> int:
            return 0

        def nth(self, index: int) -> None:
            raise AssertionError("should not be called")

        async def inner_text(self) -> str:
            return ""

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://api.monobank.ua/qr?token=url"

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

        async def content(self) -> str:
            return ""

    manager = AuthenticationManager(page=FakePage(), settings=Settings(
        check_interval_seconds=60,
        api_base_url="https://eqn.hsc.gov.ua/api/v2",
        service_id=43,
        department_id=93,
        request_method="GET",
        request_url="",
        request_headers={},
        request_body=None,
        cookie_header="",
        telegram_bot_token=None,
        telegram_chat_id=None,
        available_text_hint=None,
        service_label=None,
        department_label=None,
        browser_channel=None,
        browser_profile_dir="data/browser-profile",
        auto_login_steps=False,
    ))

    qr_url = asyncio.run(manager._extract_qr_url())
    assert qr_url == "https://api.monobank.ua/qr?token=url"


def test_qr_detection_rejects_visible_instruction_text_without_link() -> None:
    text = (
        "Авторизуйтесь через monobank\n\n"
        "Натисніть або відскануйте QR-код для авторизації з BankID через monobank"
    )
    assert not AuthenticationManager._looks_like_qr_url(text)
    assert AuthenticationManager._extract_qr_link_from_text(text) is None


def test_click_continue_button_if_present_clicks_visible_button() -> None:
    class FakeButtonLocator:
        def __init__(self) -> None:
            self.clicked = False

        async def count(self) -> int:
            return 1

        def nth(self, index: int) -> "FakeButtonLocator":
            return self

        async def is_visible(self, timeout: int = 0) -> bool:
            return True

        async def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
            return None

        async def scroll_into_view_if_needed(self) -> None:
            return None

        async def click(self, timeout: int = 0) -> None:
            self.clicked = True

    class FakeBodyLocator:
        async def inner_text(self) -> str:
            return ""

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://id.gov.ua"
            self.button = FakeButtonLocator()
            self.body = FakeBodyLocator()

        def get_by_role(self, role: str, name: str) -> FakeButtonLocator:
            return self.button

        def get_by_text(self, text: str, exact: bool = False) -> FakeButtonLocator:
            return self.button

        def locator(self, selector: str) -> FakeBodyLocator:
            return self.body

        async def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
            return None

    manager = AuthenticationManager(page=FakePage(), settings=Settings(
        check_interval_seconds=60,
        api_base_url="https://eqn.hsc.gov.ua/api/v2",
        service_id=43,
        department_id=93,
        request_method="GET",
        request_url="",
        request_headers={},
        request_body=None,
        cookie_header="",
        telegram_bot_token=None,
        telegram_chat_id=None,
        available_text_hint=None,
        service_label=None,
        department_label=None,
        browser_channel=None,
        browser_profile_dir="data/browser-profile",
        auto_login_steps=False,
    ))

    clicked = asyncio.run(manager._click_continue_button_if_present())
    assert clicked is True


def test_registration_button_visible_detects_queue_button() -> None:
    text_with_button = "Головне меню. Записатись у чергу. Мій профіль."
    text_without_button = "Будь ласка, увійдіть через BankID."
    assert AuthenticationManager.is_registration_button_visible(text_with_button)
    assert not AuthenticationManager.is_registration_button_visible(text_without_button)

