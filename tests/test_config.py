from mvsuabot.config import normalize_cookie_header


def test_normalize_cookie_header_keeps_plain_cookie() -> None:
    raw = "a=1; b=2"
    assert normalize_cookie_header(raw) == raw


def test_normalize_cookie_header_strips_set_cookie_metadata() -> None:
    raw = "session=abc; Path=/; Domain=.example.com; HttpOnly; bm_s=xyz; Secure"
    assert normalize_cookie_header(raw) == "session=abc; bm_s=xyz"
