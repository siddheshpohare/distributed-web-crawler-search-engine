"""
frontier.py — Domain-Priority URL Frontier (Phase 1 - Updated)

Instead of a plain FIFO queue, this frontier uses a min-heap keyed
by per-domain *virtual* crawl count.  The domain with the lowest
virtual count is always picked next, giving fair interleaving across
multiple seed domains while avoiding the "Dormant Flow Burst" problem.

──────────────────────────────────────────────────────────────────────
The Dormant Flow Burst problem (and why we need virtual time)
──────────────────────────────────────────────────────────────────────
If we key the heap on *lifetime* crawl counts, a domain that was
dormant (had no URLs) while other domains advanced will re-enter the
heap with a stale, very low count and monopolise the scheduler until
it "catches up" — exactly the starvation that CFS fixed in the Linux
kernel by anchoring virtual runtime to the current heap minimum.

Fix: when a domain is (re-)pushed onto the heap its key is clamped to:

    max(domain_own_count, current_heap_minimum)

A reactivating domain gets ONE turn of priority (it lands at the
floor) but not dozens — its key is never below where the slowest
active domain already sits.

Internal structure:
  _domain_queues  : dict[domain -> deque[url]]   per-domain FIFO queue
  _domain_counts  : dict[domain -> int]          pages crawled per domain
  _heap           : min-heap[(virtual_count, insertion_order, domain)]
  _in_heap        : set[str]                     dedup guard for heap
  _seen           : set[url]                     global URL deduplication

How next() works:
  1. Pop the domain with the lowest virtual count from the heap.
  2. Take the next URL from that domain's deque (FIFO within domain).
  3. If the domain still has pending URLs, re-push it with its *real*
     current count (no clamping needed — it was just active).
  4. Return the URL.

How mark_crawled() works:
  Called by main.py after a page is successfully fetched.
  Increments the domain's crawl count so it sinks in priority
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
    Domain-priority URL frontier with virtual-time anti-starvation.

    Always crawls next from the domain with the lowest *virtual* crawl
    count.  When a dormant domain reactivates, its heap key is clamped
    to ``max(own_count, current_heap_minimum)`` so it cannot consume
    dozens of consecutive turns at the expense of active domains
    (the "Dormant Flow Burst" / sleeping-process starvation problem).

    Attributes
    ----------
    _domain_queues : defaultdict[str, deque[str]]
        Per-domain FIFO queue of pending URLs.
    _domain_counts : defaultdict[str, int]
        Number of pages successfully crawled per domain.
    _heap : list[tuple[int, int, str]]
        Min-heap entries of (virtual_count, insertion_order, domain).
        insertion_order breaks ties so equal-count domains alternate
        in the order they first appeared.
    _in_heap : set[str]
        Domains currently represented in the heap (avoids duplicates).
    _seen : set[str]
        Every URL ever added — used for O(1) deduplication.
    _insertion_order : dict[str, int]
        Stable tiebreaker: the order in which each domain first appeared.
    _global_min_count : int
        The virtual-time floor — the heap key of the domain most recently
        popped.  New/reactivated domains are clamped to this value so
        they cannot burst backwards through the queue.
    """

    def __init__(self) -> None:
        self._domain_queues: defaultdict[str, deque[str]] = defaultdict(deque)
        self._domain_counts: defaultdict[str, int] = defaultdict(int)
        self._heap: list[tuple[int, int, str]] = []
        self._in_heap: set[str] = set()
        self._seen: set[str] = set()
        self._insertion_order: dict[str, int] = {}
        self._domain_counter: int = 0  # monotonic counter for new domains
        # Virtual-time floor: updated each time next() pops a domain.
        # New/dormant domains are clamped to this so they cannot burst
        # backwards and monopolise the crawler (Dormant Flow Burst fix).
        self._global_min_count: int = 0

    def _push_domain(self, domain: str) -> None:
        """Push a domain onto the heap using a clamped virtual count.

        The heap key is ``max(own_count, _global_min_count)`` — the
        virtual-time floor.  This ensures:

        1. A domain that was dormant while others advanced re-enters the
           heap at the floor (gets ONE priority slot), not 88 turns behind.
        2. A domain that is actively crawling gets pushed with its real
           count, which is already >= the floor, so clamping is a no-op.

        This is the Dormant Flow Burst fix, analogous to how CFS clamps
        a waking task's vruntime to ``min_vruntime`` before inserting it
        into the red-black tree.
        """
        if domain not in self._in_heap:
            order = self._insertion_order.setdefault(domain, self._domain_counter)
            if order == self._domain_counter:
                self._domain_counter += 1

            # Clamp: never push below the current floor.
            virtual_count = max(
                self._domain_counts[domain], self._global_min_count
            )
            heapq.heappush(self._heap, (virtual_count, order, domain))
            self._in_heap.add(domain)

    def add(self, url: str) -> bool:
        """
        Add a URL to the frontier if it has not been seen before.

        The URL is placed into its domain's FIFO queue.  The domain is
        pushed onto the min-heap with a virtual count clamped to the
        global floor so dormant domains cannot burst ahead of active ones.

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

        Selects the domain with the lowest virtual count.  Applies a
        second clamp at pop time to handle any stale heap entries that
        were enqueued *before* the floor advanced (e.g. a seed URL pushed
        at time=0 that lay dormant while other domains crawled ahead).

        After dispatching a URL, advances the floor to the effective
        virtual count so it only ever moves forward.  The domain is
        re-pushed with a fresh clamped key for its remaining URLs.

        If multiple domains share the same effective count the one seen
        first is chosen (stable insertion-order tiebreaker).

        Returns
        -------
        str | None
            The next URL, or None if the frontier is empty.
        """
        while self._heap:
            raw_count, _order, domain = heapq.heappop(self._heap)
            self._in_heap.discard(domain)

            # Pop-time clamp: correct any stale entries that slipped in
            # before the floor advanced (belt-and-suspenders with _push_domain).
            effective_count = max(raw_count, self._global_min_count)

            # Advance the floor — it only ever moves forward.
            # The +1 tick represents "one scheduling quantum consumed".
            # Without this, a domain clamped to floor=N would be re-pushed at N
            # every turn, permanently beating active domains whose count > N.
            self._global_min_count = effective_count + 1

            queue = self._domain_queues.get(domain)
            if not queue:
                # Domain exhausted its URLs — discard stale heap entry.
                continue

            url = queue.popleft()

            # Re-push: _push_domain will clamp the key to the (now updated)
            # floor, so this domain cannot jump back to the front of the heap.
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
