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
        api_calls_made = 0

        def search_single_query(idx, query_text):
            nonlocal api_calls_made
            exclusion_str = " ".join(f"-site:{site}" for site in self.excluded_sites)
            query_text_and_filter = f"{query_text} {exclusion_str}" if exclusion_str else query_text
            self.logger.info(f"[{idx + 1}/{len(queries)}] Searching '{query_text}'...")
            time.sleep(self.wait_time_between_queries)

            remaining_calls = max(0, MAX_GOOGLE_API_HITS_PER_JOB - api_calls_made)
            if remaining_calls == 0:
                self.logger.warning("API call limit reached, skipping remaining queries.")
                return []

            max_results_for_query = min(max_results_per_query, remaining_calls * 10)
            try:
                page_results, new_calls = self._get_search_results(
                    query=query_text_and_filter,
                    max_results=max_results_for_query,
                    api_calls_made=api_calls_made
                )
                api_calls_made = new_calls
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
        api_calls_made: int = 0,
        max_retries: int = 5,
        initial_wait: float = 60,  # 1 minute
        backoff_factor: float = 1.5
    ) -> tuple[list[Dict], int]:
        items_per_page = 10
        start_page = 1
        search_items = []

        while len(search_items) < max_results:
            if api_calls_made >= MAX_GOOGLE_API_HITS_PER_JOB:
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

            attempt = 0
            page_success = False
            while attempt <= max_retries and not page_success:
                try:
                    self.rate_limiter.wait()
                    response = requests.get(
                        url="https://www.googleapis.com/customsearch/v1",
                        params=params,
                        timeout=self.request_timeout
                    )
                    response.raise_for_status()
                    page_success = True
                    if attempt > 0:
                        self.logger.info(
                            f"Query '{query}', page starting at {start_page} succeeded after {attempt} retry(ies)."
                        )
                except requests.HTTPError as e:
                    status = response.status_code if 'response' in locals() else "unknown"
                    if status == 429:
                        wait_time = initial_wait * (backoff_factor ** attempt)
                        self.logger.warning(
                            f"429 Too Many Requests for query '{query}', page starting at {start_page}, "
                            f"retry {attempt + 1}/{max_retries}. Waiting {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        attempt += 1
                    else:
                        self.logger.error(
                            f"HTTP error for query '{query}', page starting at {start_page}: {e}"
                        )
                        break
                except requests.RequestException as e:
                    self.logger.error(
                        f"Request exception for query '{query}', page starting at {start_page}: {e}"
                    )
                    break
            else:
                if not page_success:
                    self.logger.error(
                        f"Max retries exceeded for query '{query}', page starting at {start_page}. Skipping this page."
                    )
                    start_page += items_per_page
                    api_calls_made += 1
                    continue

            # Process page items only if request succeeded
            data = response.json()
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
            api_calls_made += 1

        return search_items, api_calls_made


