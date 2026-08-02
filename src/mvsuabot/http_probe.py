from __future__ import annotations

from dataclasses import dataclass

from curl_cffi.requests import AsyncSession


@dataclass(frozen=True)
class ProbeResult:
    status_code: int
    text: str
    content_type: str


async def run_probe(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
) -> ProbeResult:
    if not url:
        raise ValueError("MVS_REQUEST_URL is empty. Discover the real request first.")

    async with AsyncSession(impersonate="chrome") as session:
        response = await session.request(
            method=method,
            url=url,
            headers=headers,
            data=body,
            timeout=30.0,
            allow_redirects=False,
        )

    return ProbeResult(
        status_code=response.status_code,
        text=response.text,
        content_type=response.headers.get("content-type", ""),
    )


