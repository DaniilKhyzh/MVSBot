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
