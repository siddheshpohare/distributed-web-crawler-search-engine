"""
parser.py — HTML Link Extractor (Phase 1)

Takes raw HTML and the URL it was fetched from, then returns
a list of absolute, normalized URLs found in <a href> tags.

URL normalization rules applied here:
  - Resolve relative URLs against the base URL.
  - Strip URL fragments (#section) — they point to the same page.
  - Normalize the scheme to lowercase.
  - Drop non-HTTP(S) schemes (mailto:, javascript:, ftp:, etc.).

In later phases this module will also extract the page title,
headings, and body text for the indexing pipeline.
"""

from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


# Only follow links that use these schemes.
ALLOWED_SCHEMES = {"http", "https"}


def _normalize(url: str, base_url: str) -> str | None:
    """
    Normalize a raw href value into an absolute URL.

    Parameters
    ----------
    url : str
        The raw href value found in the HTML.
    base_url : str
        The URL of the page the href was found on.  Used to
        resolve relative URLs.

    Returns
    -------
    str | None
        A normalized absolute URL, or None if the URL should
        be discarded (wrong scheme, empty, etc.).
    """
    # Resolve relative links (e.g. "../about") against the page URL.
    absolute = urljoin(base_url, url)

    parsed = urlparse(absolute)

    # Drop anything that is not http or https.
    if parsed.scheme not in ALLOWED_SCHEMES:
        return None

    # Remove the fragment (#section) — it is the same document.
    normalized = parsed._replace(fragment="")

    return urlunparse(normalized)


def extract_links(html: str, base_url: str) -> list[str]:
    """
    Parse HTML and return a deduplicated list of absolute URLs.

    Parameters
    ----------
    html : str
        Raw HTML content of the page.
    base_url : str
        The URL the HTML was fetched from.  Used to resolve
        relative href values.

    Returns
    -------
    list[str]
        Deduplicated list of valid, normalized absolute URLs
        found in <a href> tags.
    """
    soup = BeautifulSoup(html, "html.parser")

    seen_on_page: set[str] = set()
    links: list[str] = []

    for tag in soup.find_all("a", href=True):
        raw_href: str = tag["href"].strip()

        if not raw_href:
            continue

        normalized = _normalize(raw_href, base_url)

        if normalized is None:
            continue

        # Deduplicate links within this single page before returning.
        if normalized not in seen_on_page:
            seen_on_page.add(normalized)
            links.append(normalized)

    return links
