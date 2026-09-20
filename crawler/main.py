"""
main.py — Crawler Entry Point (Phase 1)

This is the top-level crawl loop for Phase 1.

Flow:
    Seed URL(s)
        ↓
    Frontier (in-memory queue)
        ↓  loop until empty or limit reached
    Fetch HTML  (fetcher.py)
        ↓
    Extract links  (parser.py)
        ↓
    Enqueue new URLs  (frontier.py)
        ↓
    Print discovered links

No database, no Redis, no async — just the core crawl loop so the
basic mechanism is clear before adding complexity.
"""

from fetcher import fetch
from frontier import Frontier
from parser import extract_links


# ── Configuration ────────────────────────────────────────────────────────────

# Starting URLs — change these to whatever you want to crawl.
SEED_URLS: list[str] = [
    "https://core-stack.org",
    
]

# Maximum number of pages to crawl before stopping.
# Set to None to crawl until the frontier is empty (be careful!).
MAX_PAGES: int = 20


# ── Crawl loop ────────────────────────────────────────────────────────────────

def crawl(seed_urls: list[str], max_pages: int | None = MAX_PAGES) -> None:
    """
    Main crawl loop.

    Parameters
    ----------
    seed_urls : list[str]
        One or more starting URLs to seed the frontier.
    max_pages : int | None
        Stop after crawling this many pages.  None means no limit.
    """
    frontier = Frontier()

    # Seed the frontier.
    for url in seed_urls:
        frontier.add(url)
        print(f"[SEED]    {url}")

    pages_crawled = 0

    while not frontier.is_empty():
        if max_pages is not None and pages_crawled >= max_pages:
            print(f"\n[DONE] Reached max page limit ({max_pages}).")
            break

        url = frontier.next()
        print(f"\n[CRAWL]   ({pages_crawled + 1}) {url}")

        # ── Step 1: Fetch HTML ────────────────────────────────────────────────
        html = fetch(url)

        if html is None:
            print(f"[SKIP]    Failed to fetch — skipping.")
            continue

        pages_crawled += 1

        # ── Step 2: Extract links ─────────────────────────────────────────────
        links = extract_links(html, base_url=url)

        print(f"[LINKS]   Found {len(links)} link(s) on this page.")

        # ── Step 3: Enqueue new URLs ──────────────────────────────────────────
        new_count = 0
        for link in links:
            added = frontier.add(link)
            if added:
                new_count += 1

        print(f"[QUEUE]   {new_count} new URL(s) added | "
              f"Queue size: {frontier.queue_size()} | "
              f"Seen total: {frontier.seen_count()}")

    print(f"\n[SUMMARY] Pages crawled: {pages_crawled} | "
          f"Unique URLs seen: {frontier.seen_count()}")


if __name__ == "__main__":
    crawl(SEED_URLS, MAX_PAGES)
