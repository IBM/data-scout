## RUN GOOGLE SEARCH QUERIES
import time
import requests
from tqdm import tqdm
from typing import List, Dict
import time

#TO DO:
#1. Add show_progress = True and tqdm progress bar

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
        wait_time_between_queries: float = 1.0
    ) -> None:
        self.api_key = api_key.strip()
        self.cx_key = cx_key.strip()
        self.request_timeout = request_timeout
        self.wait_time_between_queries = wait_time_between_queries

    def perform_search(
        self,
        queries: List[str],
        max_results_per_query: int = 10,
    ) -> List[Dict]:
        """
        Search multiple queries and collect results.

        Args:
            queries (List[str]): List of search strings.
            max_results_per_query (int): Max number of results per query.

        Returns:
            List[Dict]: List of search results enriched with metadata.
        """

        results = []

        for idx, query_text in enumerate(queries):
            print(f"[{idx+1}/{len(queries)}] Searching '{query_text}'...")
            time.sleep(self.wait_time_between_queries)
            page_results = self._get_search_results(
                query=query_text,
                max_results=max_results_per_query
            )
            results.extend(page_results)

        return results

    def _get_search_results(
        self,
        query: str,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Fetch paginated results for a single search query.

        Args:
            query: Search string.
            max_results: Maximum number of results desired per query.

        Returns:
            List[Dict]: Search items enriched with metadata fields (`search_query`, `start_page`).
        """
        items_per_page = 10
        start_page = 1
        search_items = []

        try:
            while len(search_items) < max_results:
                params = {
                    "q": query.encode("utf-8") if isinstance(query, str) else query,
                    "cx": self.cx_key,
                    "key": self.api_key,
                    "start": start_page
                }

                response = requests.get(
                    url="https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=self.request_timeout
                )

                response.raise_for_status()  # Raise HTTPError for bad responses

                data = response.json()
                page_items = data.get("items", [])

                # Stop if nothing more available or we've already collected enough
                remaining_needed = max_results - len(search_items)
                added = page_items[:remaining_needed]
                search_items.extend(added)

                # Annotate metadata fields
                for item in added:
                    item["search_query"] = query
                    item["start_page"] = start_page

                # Break loop early if no more results are coming
                if not page_items:
                    break

                start_page += items_per_page  # Fixed step increment logic per original intent

        except requests.exceptions.RequestException as e:
            print(f"[!] Request error fetching results for '{query}': {str(e)}")
        except Exception as e:
            print(f"[!] Other error fetching results: {str(e)}")

        return search_items