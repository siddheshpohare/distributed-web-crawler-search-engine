"""
fetcher.py — HTTP Fetcher (Phase 1)

Responsible for making a single HTTP GET request to a URL and
returning the raw HTML content.

Uses httpx (sync client) with a configurable timeout.
In later phases this will handle retries, exponential backoff,
and per-domain rate limiting.
"""

import httpx


# How long to wait (seconds) before giving up on a request.
DEFAULT_TIMEOUT = 10.0

# User-Agent sent with every request so servers know who we are.
USER_AGENT = (
    "DistributedCrawlerBot/0.1 "
    "(educational project; +https://github.com/you/your-repo)"
)


def fetch(url: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """
    Perform a synchronous HTTP GET request and return the HTML body.

    Parameters
    ----------
    url : str
        The URL to fetch.
    timeout : float
        Request timeout in seconds. Defaults to DEFAULT_TIMEOUT.

    Returns
    -------
    str | None
        The decoded response body if the request succeeded (HTTP 200),
        or None on any error (network failure, timeout, non-200 status).
    """
    headers = {"User-Agent": USER_AGENT}

    try:
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()  # raises httpx.HTTPStatusError on 4xx/5xx
        return response.text

    except httpx.HTTPStatusError as exc:
        print(f"[FETCHER] HTTP error {exc.response.status_code} for {url}")
    except httpx.TimeoutException:
        print(f"[FETCHER] Timeout fetching {url}")
    except httpx.RequestError as exc:
        # Covers DNS failures, connection resets, etc.
        print(f"[FETCHER] Network error fetching {url}: {exc}")

    return None
