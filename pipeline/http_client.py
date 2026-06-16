from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


USER_AGENT = (
    "placsp-pharma-tender-pipeline/0.1 "
    "(student take-home assignment; "
    "contact: replace-with-your-email@example.com)"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


class PoliteSession:
    """A `requests.Session` that rate-limits and retries automatically.

    Parameters
    ----------
    min_delay_seconds:
        Minimum time to wait between the *start* of one request and the
        start of the next. Applied even after failed requests, so retries
        don't bypass the rate limit.
    max_retries:
        How many times to retry a request that times out or returns a
        5xx server error, before giving up and raising.
    backoff_factor:
        Each retry waits `backoff_factor * attempt_number` seconds longer
        than the last, on top of the normal rate-limit delay.
    timeout_seconds:
        Per-request timeout passed to `requests`.
    """

    def __init__(
        self,
        min_delay_seconds: float = 1.5,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

        self.min_delay_seconds = min_delay_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout_seconds = timeout_seconds

        self._last_request_time: float | None = None

    def _wait_for_rate_limit(self) -> None:
        """Sleep if needed so we don't request faster than `min_delay_seconds`."""
        if self._last_request_time is None:
            return

        elapsed = time.monotonic() - self._last_request_time
        remaining = self.min_delay_seconds - elapsed
        if remaining > 0:
            logger.debug("Rate limiting: sleeping %.2fs", remaining)
            time.sleep(remaining)

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET `url`, applying rate limiting, retries and logging."""
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST to `url`, applying rate limiting, retries and logging."""
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout_seconds)

        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            self._last_request_time = time.monotonic()

            logger.info("%s %s (attempt %d/%d)", method, url, attempt, self.max_retries)

            try:
                response = self._session.request(method, url, **kwargs)
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                logger.warning("Request error on attempt %d: %s", attempt, exc)
            else:
                if response.status_code >= 500:
                    logger.warning(
                        "Server error %d on attempt %d for %s",
                        response.status_code,
                        attempt,
                        url,
                    )
                    last_exception = None
                else:
                    response.raise_for_status()
                    return response

            if attempt < self.max_retries:
                backoff = self.backoff_factor * attempt
                logger.debug("Backing off for %.2fs before retry", backoff)
                time.sleep(backoff)

        if last_exception is not None:
            raise last_exception

        raise RuntimeError(
            f"Giving up on {method} {url} after {self.max_retries} attempts "
            "(repeated server errors)"
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "PoliteSession":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
