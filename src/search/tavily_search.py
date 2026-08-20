import re
import time
import threading
from typing import List, Dict

import tldextract
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.processing import utils


class TavilySearchClient:
    """
    Search client wrapping the Tavily Search API, with the same interface as GoogleSearchClient.
    """

    def __init__(
        self,
        api_key: str,
        search_depth: str = "basic",
        wait_time_between_queries: float = 1.0,
    ) -> None:
        from tavily import TavilyClient
        self.client = TavilyClient(api_key=api_key.strip())
        self.search_depth = search_depth
        self.wait_time_between_queries = wait_time_between_queries
        self.logger = utils.get_default_logger()
        self._lock = threading.Lock()

    def perform_search(
        self,
        queries: List[str],
        max_results_per_query: int = 20,
        max_concurrent_queries: int = 5,
    ) -> List[Dict]:
        results = []

        def search_one(idx: int, raw_query: str) -> List[Dict]:
            clean = re.sub(r"-site:\S+", "", raw_query).strip()
            excluded = re.findall(r"-site:(\S+)", raw_query)
            excluded = list(set(excluded + ["reddit.com", "medium.com"]))

            time.sleep(self.wait_time_between_queries)
            max_retries, wait = 5, 60.0
            for attempt in range(max_retries + 1):
                try:
                    with self._lock:
                        pass  # rate limiting is handled by the sleep above
                    resp = self.client.search(
                        query=clean,
                        search_depth=self.search_depth,
                        max_results=min(max_results_per_query, 20),
                        include_answer=False,
                        exclude_domains=excluded or None,
                    )
                    hits = []
                    for r in resp.get("results", []):
                        url = r.get("url", "")
                        ext = tldextract.extract(url)
                        hits.append({
                            "title":        r.get("title"),
                            "link":         url,
                            "snippet":      r.get("content", ""),
                            "domain":       ext.domain if ext.domain else None,
                            "search_query": raw_query,
                            "score":        r.get("score"),
                        })
                    self.logger.info(f"[{idx + 1}/{len(queries)}] Tavily '{clean}': {len(hits)} results")
                    return hits
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries:
                        self.logger.warning(f"429 for '{clean}', retry {attempt + 1}, waiting {wait:.0f}s")
                        time.sleep(wait)
                        wait *= 1.5
                    else:
                        self.logger.error(f"Tavily error for '{clean}': {e}")
                        return []
            return []

        with ThreadPoolExecutor(max_workers=max_concurrent_queries) as executor:
            futures = [executor.submit(search_one, idx, q) for idx, q in enumerate(queries)]
            for f in tqdm(as_completed(futures), total=len(futures), desc="Searching"):
                try:
                    results.extend(f.result())
                except Exception as e:
                    self.logger.error(f"Unexpected error: {e}")

        return results
