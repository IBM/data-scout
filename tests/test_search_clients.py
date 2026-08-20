import pytest
from unittest.mock import patch, MagicMock
from src.search.google_search import GoogleSearchClient, RateLimiter
from src.search.tavily_search import TavilySearchClient


class TestGoogleSearchClientInit:
    def test_stores_credentials(self):
        client = GoogleSearchClient("api-key", "cx-key")
        assert client.api_key == "api-key"
        assert client.cx_key == "cx-key"

    def test_strips_whitespace(self):
        client = GoogleSearchClient("  key  ", "  cx  ")
        assert client.api_key == "key"
        assert client.cx_key == "cx"


class TestGoogleSearchPerformSearch:
    @patch("src.search.google_search.requests.get")
    def test_basic_search(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"title": "Result 1", "link": "https://example.com/page1"},
                {"title": "Result 2", "link": "https://test.org/page2"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = GoogleSearchClient("key", "cx", wait_time_between_queries=0)
        results = client.perform_search(["test query"], max_results_per_query=10)

        assert len(results) >= 1
        mock_get.assert_called()

    @patch("src.search.google_search.requests.get")
    def test_adds_site_exclusions(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = GoogleSearchClient("key", "cx", wait_time_between_queries=0)
        client.perform_search(["my query"], max_results_per_query=10)

        call_args = mock_get.call_args
        query_param = call_args[1]["params"]["q"]
        if isinstance(query_param, bytes):
            query_param = query_param.decode()
        assert "-site:reddit.com" in query_param
        assert "-site:medium.com" in query_param

    @patch("src.search.google_search.requests.get")
    def test_domain_extraction(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{"title": "T", "link": "https://www.example.com/page"}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = GoogleSearchClient("key", "cx", wait_time_between_queries=0)
        results = client.perform_search(["query"], max_results_per_query=10)

        assert results[0]["domain"] == "example"

    @patch("src.search.google_search.requests.get")
    def test_empty_results(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = GoogleSearchClient("key", "cx", wait_time_between_queries=0)
        results = client.perform_search(["query"], max_results_per_query=10)
        assert results == []


class TestRateLimiter:
    def test_first_call_no_wait(self):
        limiter = RateLimiter(min_interval=1.0)
        import time
        start = time.time()
        limiter.wait()
        elapsed = time.time() - start
        assert elapsed < 0.1


class TestTavilySearchClientInit:
    @patch("tavily.TavilyClient")
    def test_stores_search_depth(self, mock_tavily):
        client = TavilySearchClient("key", search_depth="advanced")
        assert client.search_depth == "advanced"


class TestTavilySearchPerformSearch:
    @patch("tavily.TavilyClient")
    def test_basic_search(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.return_value = {
            "results": [
                {"title": "Result", "url": "https://example.com/page", "content": "snippet", "score": 0.9}
            ]
        }

        client = TavilySearchClient("key", wait_time_between_queries=0)
        results = client.perform_search(["test query"], max_results_per_query=5)

        assert len(results) == 1
        assert results[0]["title"] == "Result"
        assert results[0]["link"] == "https://example.com/page"
        assert results[0]["snippet"] == "snippet"
        assert results[0]["domain"] == "example"

    @patch("tavily.TavilyClient")
    def test_strips_site_exclusions_from_query(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        client = TavilySearchClient("key", wait_time_between_queries=0)
        client.perform_search(["query -site:reddit.com -site:medium.com"], max_results_per_query=5)

        call_args = mock_client.search.call_args
        assert "-site:" not in call_args[1]["query"]
        assert "reddit.com" in call_args[1]["exclude_domains"]

    @patch("tavily.TavilyClient")
    def test_handles_error(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.side_effect = Exception("API error")

        client = TavilySearchClient("key", wait_time_between_queries=0)
        results = client.perform_search(["query"], max_results_per_query=5)
        assert results == []
