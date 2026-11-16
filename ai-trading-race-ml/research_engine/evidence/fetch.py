"""Allowlisted HTTP fetcher with manual redirect validation (spec 18.4).

* Only ``https`` URLs on an exact allowlisted host are fetched.
* Redirects are never followed automatically: each ``Location`` is resolved and
  re-validated against the allowlist before the next request.
* Requests are sequential with a politeness delay; transient failures are
  retried with bounded backoff (``RetryPolicy``).
* Agent tools never reach this module; only source adapters do.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from research_engine.contracts.evidence import RetryPolicy

USER_AGENT = (
    "fi-research-lab/0.1 (+fixed income research platform; evidence fixture collection; "
    "sequential requests)"
)


class HostNotAllowed(ValueError):
    """URL or redirect target outside the source allowlist."""


class FetchError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status: Optional[int] = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: int
    content: bytes
    content_type: str
    last_modified: Optional[str]
    etag: Optional[str]
    redirects: tuple[str, ...]
    fetched_at: datetime
    attempts: int = 1


def validate_url(url: str, allowed_hosts: list[str] | tuple[str, ...]) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise HostNotAllowed(f"only https URLs are permitted: {url!r}")
    if parts.username or parts.password:
        raise HostNotAllowed(f"credentials in URL are not permitted: {url!r}")
    host = (parts.hostname or "").lower()
    if host not in {h.lower() for h in allowed_hosts}:
        raise HostNotAllowed(f"host {host!r} is not in the source allowlist")
    if parts.port not in (None, 443):
        raise HostNotAllowed(f"non-default port is not permitted: {url!r}")
    return url


@dataclass
class AllowlistedFetcher:
    allowed_hosts: tuple[str, ...]
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    max_redirects: int = 3
    transport: Optional[httpx.BaseTransport] = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    _last_request: Optional[float] = None

    def _client(self) -> httpx.Client:
        return httpx.Client(
            follow_redirects=False,
            timeout=self.retry.request_timeout_seconds,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf"},
            transport=self.transport,
        )

    def _polite(self) -> None:
        delay = self.retry.politeness_delay_ms / 1000.0
        if self._last_request is not None and delay > 0:
            elapsed = time.monotonic() - self._last_request
            if elapsed < delay:
                self.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    def _once(self, client: httpx.Client, url: str) -> FetchResult:
        current = validate_url(url, self.allowed_hosts)
        redirects: list[str] = []
        for _ in range(self.max_redirects + 1):
            self._polite()
            try:
                response = client.get(current)
            except httpx.HTTPError as exc:
                raise FetchError(f"transport error for {current}: {exc}", retryable=True) from exc
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("redirect without Location", retryable=False)
                target = urljoin(current, location)
                validate_url(target, self.allowed_hosts)  # raises HostNotAllowed
                redirects.append(target)
                current = target
                continue
            if response.status_code in (408, 429) or response.status_code >= 500:
                raise FetchError(
                    f"HTTP {response.status_code} for {current}",
                    retryable=True,
                    status=response.status_code,
                )
            if response.status_code != 200:
                raise FetchError(
                    f"HTTP {response.status_code} for {current}",
                    retryable=False,
                    status=response.status_code,
                )
            return FetchResult(
                url=url,
                final_url=current,
                status=response.status_code,
                content=response.content,
                content_type=response.headers.get("content-type", ""),
                last_modified=response.headers.get("last-modified"),
                etag=response.headers.get("etag"),
                redirects=tuple(redirects),
                fetched_at=self.clock(),
            )
        raise FetchError(f"too many redirects for {url}", retryable=False)

    def fetch(self, url: str) -> FetchResult:
        attempts = 0
        last: Optional[FetchError] = None
        with self._client() as client:
            while attempts < max(1, self.retry.max_attempts):
                attempts += 1
                try:
                    result = self._once(client, url)
                    return FetchResult(**{**result.__dict__, "attempts": attempts})
                except FetchError as exc:
                    last = exc
                    if not exc.retryable or attempts >= self.retry.max_attempts:
                        break
                    backoff = self.retry.backoff_seconds
                    self.sleep(backoff[min(attempts - 1, len(backoff) - 1)] if backoff else 0)
        assert last is not None
        raise last
