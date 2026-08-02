import asyncio

from mvsuabot.equeue import _raise_for_status
from mvsuabot.http_probe import ProbeResult
from mvsuabot.session_manager import SessionManager


def test_raise_for_status_allows_204_no_content() -> None:
    _raise_for_status(ProbeResult(status_code=204, text="", content_type="application/json"))


def test_session_manager_fetch_json_treats_204_as_empty_payload() -> None:
    class DummySessionManager(SessionManager):
        async def _fetch(self, url: str) -> tuple[int, str]:
            return 204, ""

    manager = DummySessionManager()

    async def run() -> None:
        assert await manager.fetch_json("https://example.test") == []

    asyncio.run(run())
