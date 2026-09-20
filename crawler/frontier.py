"""
frontier.py — In-memory URL Frontier (Phase 1)

Manages the set of URLs waiting to be crawled and tracks
which URLs have already been seen, preventing duplicate work.

In later phases this will be replaced by a Redis-backed queue
so multiple crawler workers can share the frontier atomically.
"""

from collections import deque


class Frontier:
    """
    Simple in-memory URL frontier backed by a deque (FIFO).

    Attributes
    ----------
    _queue : deque[str]
        URLs waiting to be crawled, processed in FIFO order.
    _seen : set[str]
        URLs that have already been added (visited or queued).
        Used to prevent the same URL from being enqueued twice.
    """

    def __init__(self) -> None:
        self._queue: deque[str] = deque()
        self._seen: set[str] = set()

    def add(self, url: str) -> bool:
        """
        Add a URL to the frontier if it has not been seen before.

        Parameters
        ----------
        url : str
            The URL to add.

        Returns
        -------
        bool
            True if the URL was newly added, False if it was
            already present in the seen set (duplicate).
        """
        if url in self._seen:
            return False
        self._seen.add(url)
        self._queue.append(url)
        return True

    def next(self) -> str | None:
        """
        Return the next URL to crawl (FIFO order).

        Returns
        -------
        str | None
            The next URL, or None if the queue is empty.
        """
        if self._queue:
            return self._queue.popleft()
        return None

    def is_empty(self) -> bool:
        """Return True when there are no more URLs to crawl."""
        return len(self._queue) == 0

    def seen_count(self) -> int:
        """Return the total number of unique URLs seen so far."""
        return len(self._seen)

    def queue_size(self) -> int:
        """Return how many URLs are currently waiting in the queue."""
        return len(self._queue)
