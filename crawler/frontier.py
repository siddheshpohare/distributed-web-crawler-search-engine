"""
frontier.py — Domain-Priority URL Frontier (Phase 1 - Updated)

Instead of a plain FIFO queue, this frontier uses a min-heap keyed
by per-domain crawl count.  The domain with the fewest pages crawled
is always picked next, ensuring fair interleaving across multiple
seed domains.

Internal structure:
  _domain_queues  : dict[domain -> deque[url]]   per-domain FIFO queue
  _domain_counts  : dict[domain -> int]          pages crawled per domain
  _heap           : min-heap[(crawl_count, domain)]  one entry per domain
                    that currently has pending URLs
  _seen           : set[url]                     global deduplication

How next() works:
  1. Pop the domain with the lowest crawl count from the heap.
  2. Take the next URL from that domain's deque (FIFO within domain).
  3. If the domain still has more URLs, re-push it with its current count.
  4. Return the URL.

How mark_crawled() works:
  Called by main.py after a page is successfully fetched.
  Increments the domain's crawl count so it sinks lower in priority
  relative to less-crawled domains.

In later phases this will be replaced by a Redis-backed queue
so multiple crawler workers can share the frontier atomically.
"""

import heapq
from collections import defaultdict, deque
from urllib.parse import urlparse


def _domain(url: str) -> str:
    """Extract the netloc (hostname) from a URL."""
    return urlparse(url).netloc


class Frontier:
    """
    Domain-priority URL frontier.

    Always crawls next from the domain with the fewest pages crawled,
    giving fair interleaving when multiple seed domains are present.

    Attributes
    ----------
    _domain_queues : defaultdict[str, deque[str]]
        Per-domain FIFO queue of pending URLs.
    _domain_counts : defaultdict[str, int]
        Number of pages successfully crawled per domain.
    _heap : list[tuple[int, int, str]]
        Min-heap entries of (crawl_count, insertion_order, domain).
        insertion_order breaks ties so equal-count domains alternate
        in the order they first appeared.
    _in_heap : set[str]
        Domains currently represented in the heap (avoids duplicates).
    _seen : set[str]
        Every URL ever added — used for O(1) deduplication.
    _insertion_order : dict[str, int]
        Stable tiebreaker: the order in which each domain first appeared.
    """

    def __init__(self) -> None:
        self._domain_queues: defaultdict[str, deque[str]] = defaultdict(deque)
        self._domain_counts: defaultdict[str, int] = defaultdict(int)
        self._heap: list[tuple[int, int, str]] = []
        self._in_heap: set[str] = set()
        self._seen: set[str] = set()
        self._insertion_order: dict[str, int] = {}
        self._domain_counter: int = 0  # monotonic counter for new domains

    def _push_domain(self, domain: str) -> None:
        """Push a domain onto the heap if it is not already there."""
        if domain not in self._in_heap:
            order = self._insertion_order.setdefault(domain, self._domain_counter)
            if order == self._domain_counter:
                self._domain_counter += 1
            heapq.heappush(
                self._heap,
                (self._domain_counts[domain], order, domain),
            )
            self._in_heap.add(domain)

    def add(self, url: str) -> bool:
        """
        Add a URL to the frontier if it has not been seen before.

        The URL is placed into its domain's FIFO queue.  The domain is
        pushed onto the min-heap keyed by current crawl count so domains
        with fewer crawls are preferred.

        Parameters
        ----------
        url : str
            The absolute URL to add.

        Returns
        -------
        bool
            True if the URL was newly added, False if it was a duplicate.
        """
        if url in self._seen:
            return False

        self._seen.add(url)
        domain = _domain(url)
        self._domain_queues[domain].append(url)
        self._push_domain(domain)
        return True

    def next(self) -> str | None:
        """
        Return the next URL to crawl.

        Selects the domain with the lowest crawl count (highest priority).
        If multiple domains share the same count, the one that was seen
        first is chosen (stable insertion-order tiebreaker).

        Returns
        -------
        str | None
            The next URL, or None if the frontier is empty.
        """
        while self._heap:
            _count, _order, domain = heapq.heappop(self._heap)
            self._in_heap.discard(domain)

            queue = self._domain_queues.get(domain)
            if not queue:
                # Domain exhausted its URLs — skip.
                continue

            url = queue.popleft()

            # If the domain still has pending URLs, re-push it with the
            # latest crawl count so its position reflects new information.
            if queue:
                self._push_domain(domain)

            return url

        return None

    def mark_crawled(self, url: str) -> None:
        """
        Notify the frontier that a URL was successfully crawled.

        Increments the crawl count for the URL's domain.  This causes
        the domain to sink lower in priority relative to domains that
        have been crawled less.

        Call this from main.py after a successful fetch + parse.

        Parameters
        ----------
        url : str
            The URL that was just successfully crawled.
        """
        domain = _domain(url)
        self._domain_counts[domain] += 1

    def is_empty(self) -> bool:
        """Return True when there are no more URLs to crawl."""
        return len(self._heap) == 0 and all(
            len(q) == 0 for q in self._domain_queues.values()
        )

    def seen_count(self) -> int:
        """Return the total number of unique URLs seen so far."""
        return len(self._seen)

    def queue_size(self) -> int:
        """Return how many URLs are currently waiting across all domains."""
        return sum(len(q) for q in self._domain_queues.values())

    def domain_stats(self) -> dict[str, int]:
        """
        Return a snapshot of crawl counts per domain.

        Useful for logging / debugging to see how balanced the crawl is.

        Returns
        -------
        dict[str, int]
            Mapping of domain -> pages crawled, sorted by count descending.
        """
        return dict(
            sorted(self._domain_counts.items(), key=lambda x: x[1], reverse=True)
        )
