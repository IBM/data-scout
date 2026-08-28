## RUN GOOGLE SEARCH QUERIES
import time
import requests
from tqdm import tqdm
from typing import List, Dict
import time
import tldextract
from src.processing import utils
from src.limits import MAX_GOOGLE_API_HITS_PER_JOB
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

#TO DO:
#1. Add show_progress = True and tqdm progress bar

class CallBudget:
    """Thread-safe counter for the per-job Google API call budget.

    The budget used to live in a `nonlocal int` that five concurrent threads
    read, incremented locally, and wrote back over each other -- so
    MAX_GOOGLE_API_HITS_PER_JOB was advisory at best. Reserving through a lock
    makes it actually hold.
    """

    def __init__(self, limit: int):
        self._limit = limit
        self._used = 0
        self._lock = threading.Lock()

    def reserve(self, n: int = 1) -> int:
        """Claim up to n calls, returning how many were actually granted."""
        with self._lock:
            granted = max(0, min(n, self._limit - self._used))
            self._used += granted
            return granted

    def release(self, n: int = 1) -> None:
        """Return unused reserved calls to the budget."""
        with self._lock:
            self._used = max(0, self._used - n)

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self._limit - self._used)


class RateLimiter:
    def __init__(self, min_interval: float):
        self.lock = threading.Lock()
        self.min_interval = min_interval
        self.last_time = 0

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_time = time.time()

class GoogleSearchClient:
    """
    A wrapper class for interacting with Google Custom Search API.
    
    Attributes:
        api_key (str): Your Google Cloud Platform API key for the Custom Search Engine API.
        cx_key (str): Identifier of your Google Custom Search Engine.
        request_timeout (int): Timeout duration for HTTP requests in seconds.
        wait_time_between_queries (float): Time delay between successive queries to avoid rate limiting.
    """

    def __init__(
        self,
        api_key: str,
        cx_key: str,
        request_timeout: int = 5,
        wait_time_between_queries: float = 1.0,
        excluded_sites: list[str] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.cx_key = cx_key.strip()
        self.request_timeout = request_timeout
        self.wait_time_between_queries = wait_time_between_queries
        self.excluded_sites = excluded_sites if excluded_sites is not None else ["reddit.com", "medium.com"]
        self.logger = utils.get_default_logger()
        self.rate_limiter = RateLimiter(min_interval=1.0)

    def perform_search(
        self,
        queries: List[str],
        max_results_per_query: int = 20,
        max_concurrent_queries: int = 5,  # tune this
    ) -> List[Dict]:
        results = []
        budget = CallBudget(MAX_GOOGLE_API_HITS_PER_JOB)

        def search_single_query(idx, query_text):
            exclusion_str = " ".join(f"-site:{site}" for site in self.excluded_sites)
            query_text_and_filter = f"{query_text} {exclusion_str}" if exclusion_str else query_text
            self.logger.info(f"[{idx + 1}/{len(queries)}] Searching '{query_text}'...")
            time.sleep(self.wait_time_between_queries)

            if budget.remaining == 0:
                self.logger.warning("API call limit reached, skipping remaining queries.")
                return []

            max_results_for_query = min(max_results_per_query, budget.remaining * 10)
            try:
                page_results, _ = self._get_search_results(
                    query=query_text_and_filter,
                    max_results=max_results_for_query,
                    budget=budget,
                )
                return page_results
            except Exception as e:
                self.logger.error(f"Failed to get results for query '{query_text}': {e}")
                return []

        # Run multiple queries concurrently
        with ThreadPoolExecutor(max_workers=max_concurrent_queries) as executor:
            futures = [
                executor.submit(search_single_query, idx, query)
                for idx, query in enumerate(queries)
            ]

            for f in tqdm(as_completed(futures), total=len(futures), desc="Searching"):
                try:
                    query_results = f.result()
                    results.extend(query_results)
                except Exception as e:
                    self.logger.error(f"Unexpected query error: {e}")

        return results

    def _get_search_results(
        self,
        query: str,
        max_results: int = 10,
        budget: "CallBudget | None" = None,
        max_retries: int = 5,
        initial_wait: float = 60,  # 1 minute
        backoff_factor: float = 1.5
    ) -> tuple[list[Dict], int]:
        items_per_page = 10
        start_page = 1
        search_items = []
        if budget is None:
            budget = CallBudget(MAX_GOOGLE_API_HITS_PER_JOB)

        while len(search_items) < max_results:
            # Reserve before spending. A page that fails still consumed the quota
            # at Google's end, so the reservation is deliberately not released.
            if not budget.reserve(1):
                self.logger.warning(
                    f"API call limit reached inside _get_search_results for query '{query}', stopping."
                )
                break

            params = {
                "q": query.encode("utf-8") if isinstance(query, str) else query,
                "cx": self.cx_key,
                "key": self.api_key,
                "start": start_page
            }

            # Bound before the retry loop. Previously a non-429 HTTPError or any
            # RequestException `break`ed straight past the loop's `else` and fell
            # into `response.json()` -- raising UnboundLocalError on the first
            # page, and silently re-parsing the *previous* page on later ones. A
            # 4xx body also parsed as an empty result page, so a bad API key
            # looked like "no results" rather than an error.
            response = None
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    self.rate_limiter.wait()
                    candidate = requests.get(
                        url="https://www.googleapis.com/customsearch/v1",
                        params=params,
                        timeout=self.request_timeout
                    )
                    candidate.raise_for_status()
                    response = candidate
                    if attempt > 0:
                        self.logger.info(
                            f"Query '{query}', page starting at {start_page} succeeded after {attempt} retry(ies)."
                        )
                    break
                except requests.HTTPError as e:
                    last_error = e
                    status = getattr(e.response, "status_code", None)
                    if status == 429 and attempt < max_retries:
                        wait_time = initial_wait * (backoff_factor ** attempt)
                        self.logger.warning(
                            f"429 Too Many Requests for query '{query}', page starting at {start_page}, "
                            f"retry {attempt + 1}/{max_retries}. Waiting {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    # Anything else (401 bad key, 403 quota, 404 bad cx) will not
                    # improve on retry: report the real status and give up.
                    self.logger.error(
                        f"HTTP {status} for query '{query}', page starting at {start_page}: {e}"
                    )
                    break
                except requests.RequestException as e:
                    last_error = e
                    self.logger.error(
                        f"Request exception for query '{query}', page starting at {start_page}: {e}"
                    )
                    break

            if response is None:
                self.logger.error(
                    f"Giving up on query '{query}' at page {start_page}: {last_error}"
                )
                break

            try:
                data = response.json()
            except ValueError as e:
                self.logger.error(f"Non-JSON response for query '{query}', page {start_page}: {e}")
                break

            page_items = data.get("items", [])

            remaining_needed = max_results - len(search_items)
            added = page_items[:remaining_needed]
            search_items.extend(added)

            for item in added:
                item["search_query"] = query
                item["start_page"] = start_page
                link = item.get("link")
                if link:
                    ext = tldextract.extract(link)
                    item["domain"] = ext.domain if ext.domain else None
                else:
                    item["domain"] = None

            if not page_items:
                self.logger.info(f"No more results for query '{query}', page starting at {start_page}.")
                break

            start_page += items_per_page

        return search_items, budget.used
