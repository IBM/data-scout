import re
import time
from typing import List, Dict

import tldextract
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.limits import TAVILY_MAX_RESULTS_PER_QUERY
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
        excluded_sites: list[str] | None = None,
    ) -> None:
        from tavily import TavilyClient
        self.client = TavilyClient(api_key=api_key.strip())
        self.search_depth = search_depth
        self.wait_time_between_queries = wait_time_between_queries
        # Same default and the same source of truth as GoogleSearchClient: this
        # used to hardcode the two domains and ignore settings.excluded_sites, so
        # the two providers honoured different exclusion lists.
        self.excluded_sites = excluded_sites if excluded_sites is not None else ["reddit.com", "medium.com"]
        self.logger = utils.get_default_logger()

    def perform_search(
        self,
        queries: List[str],
        max_results_per_query: int = 20,
        max_concurrent_queries: int = 5,
    ) -> List[Dict]:
        results = []

        # Reported once per call, not per query: Tavily caps a single request at
        # TAVILY_MAX_RESULTS_PER_QUERY, while MAX_RESULTS_PER_QUERY_LIMIT is 1000
        # and the CLI advertises "max: 1000". Silently capping made the difference
        # invisible.
        capped = min(max_results_per_query, TAVILY_MAX_RESULTS_PER_QUERY)
        if max_results_per_query > TAVILY_MAX_RESULTS_PER_QUERY:
            self.logger.warning(
                f"Tavily returns at most {TAVILY_MAX_RESULTS_PER_QUERY} results per query; "
                f"max_results_per_query={max_results_per_query} will yield {capped}. "
                "Use the Google provider for more, or raise recursion depth for more queries."
            )

        def search_one(idx: int, raw_query: str) -> List[Dict]:
            clean = re.sub(r"-site:\S+", "", raw_query).strip()
            excluded = re.findall(r"-site:(\S+)", raw_query)
            excluded = list(set(excluded + list(self.excluded_sites)))

            time.sleep(self.wait_time_between_queries)
            max_retries, wait = 5, 60.0
            for attempt in range(max_retries + 1):
                try:
                    resp = self.client.search(
                        query=clean,
                        search_depth=self.search_depth,
                        max_results=capped,
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
