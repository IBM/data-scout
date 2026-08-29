# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import concurrent.futures as cf
import threading
import requests as R
import src.search.google_search as g
from unittest.mock import Mock
import pytest
from unittest.mock import patch, MagicMock
from src.search.google_search import GoogleSearchClient, RateLimiter
from src.search.tavily_search import TavilySearchClient
from src.limits import TAVILY_MAX_RESULTS_PER_QUERY
import inspect
import logging


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


def _tavily(**kw):
    with patch("tavily.TavilyClient"):
        return TavilySearchClient(api_key="k", **kw)


class TestTavilyMatchesGoogle:
    def test_dead_lock_is_gone(self):
        assert not hasattr(_tavily(), "_lock")

    def test_excluded_sites_reach_the_api_call(self):
        """It hardcoded reddit/medium and ignored settings.excluded_sites, so the
        two providers honoured different exclusion lists. Asserting on the
        constructor attribute alone does not catch that -- the hardcoded list was
        inside the search call."""
        client = _tavily(excluded_sites=["example.com", "blocked.org"])
        client.wait_time_between_queries = 0
        client.client.search = MagicMock(return_value={"results": []})

        client.perform_search(["some query"], max_results_per_query=5)

        excluded = client.client.search.call_args.kwargs["exclude_domains"]
        assert set(excluded) == {"example.com", "blocked.org"}, (
            f"settings.excluded_sites did not reach Tavily; got {excluded}"
        )

    def test_hardcoded_defaults_are_not_forced_in(self):
        client = _tavily(excluded_sites=["only-this.com"])
        client.wait_time_between_queries = 0
        client.client.search = MagicMock(return_value={"results": []})

        client.perform_search(["q"], max_results_per_query=5)

        excluded = client.client.search.call_args.kwargs["exclude_domains"]
        assert "reddit.com" not in excluded

    def test_default_matches_google_when_unset(self):
        assert _tavily().excluded_sites == ["reddit.com", "medium.com"]

    def test_pipeline_passes_excluded_sites_through(self):
        from src.pipeline import pipeline as pipeline_module

        source = inspect.getsource(pipeline_module)
        assert "TavilySearchClient(" in source
        tavily_call = source.split("TavilySearchClient(")[1].split(")")[0]
        assert "excluded_sites" in tavily_call

    def test_cap_above_tavilys_limit_is_reported(self, caplog):
        """It silently capped at 20 while the CLI advertises max 1000."""
        client = _tavily()
        client.logger = logging.getLogger("test-tavily-cap")

        with caplog.at_level(logging.WARNING, logger="test-tavily-cap"):
            client.perform_search([], max_results_per_query=500)

        assert "at most 20" in caplog.text

    def test_no_warning_within_the_limit(self, caplog):
        client = _tavily()
        client.logger = logging.getLogger("test-tavily-nocap")

        with caplog.at_level(logging.WARNING, logger="test-tavily-nocap"):
            client.perform_search([], max_results_per_query=10)

        assert "at most" not in caplog.text


def _client():
    c = g.GoogleSearchClient("k", "cx", wait_time_between_queries=0)
    c.rate_limiter = g.RateLimiter(min_interval=0)
    return c


def _ok_page(items):
    r = Mock(status_code=200)
    r.raise_for_status.return_value = None
    r.json.return_value = {"items": items}
    return r


def _err_page(status, body=None):
    r = Mock(status_code=status)
    r.raise_for_status.side_effect = R.HTTPError(f"{status}", response=r)
    r.json.return_value = body if body is not None else {"error": {"code": status}}
    return r


class TestGoogleErrorPaths:
    """#1 -- a network error used to raise UnboundLocalError from response.json()."""

    def test_request_exception_returns_empty_not_unbound_local(self):
        with patch.object(g.requests, "get", side_effect=R.exceptions.ConnectTimeout("boom")):
            items, _ = _client()._get_search_results("q", max_results=10)
        assert items == []

    def test_connection_error_does_not_raise(self):
        with patch.object(g.requests, "get", side_effect=R.exceptions.ConnectionError("down")):
            items, _ = _client()._get_search_results("q", max_results=10)
        assert items == []

    def test_error_body_is_never_parsed_as_results(self):
        """A 401 body used to be read by response.json() and treated as a page."""
        resp = _err_page(401, {"items": [{"link": "https://leaked.example/x"}]})
        with patch.object(g.requests, "get", return_value=resp):
            items, _ = _client()._get_search_results("q", max_results=10)
        assert items == []
        assert not resp.json.called, "error body must not be parsed as a results page"

    def test_non_retryable_status_is_not_retried(self):
        """401/403/404 will not improve on retry; only 429 should back off."""
        resp = _err_page(401)
        with patch.object(g.requests, "get", return_value=resp) as get:
            _client()._get_search_results("q", max_results=10)
        assert get.call_count == 1

    def test_stale_response_not_reused_on_later_page(self):
        """Page 1 succeeds, page 2 errors: page 1's items must not be re-added."""
        seq = [_ok_page([{"link": f"https://e.com/{i}"} for i in range(10)]),
               _err_page(500)]
        with patch.object(g.requests, "get", side_effect=seq):
            items, _ = _client()._get_search_results("q", max_results=30)
        assert len(items) == 10
        assert len({i["link"] for i in items}) == 10

    def test_non_json_body_does_not_raise(self):
        resp = Mock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("not json")
        with patch.object(g.requests, "get", return_value=resp):
            items, _ = _client()._get_search_results("q", max_results=10)
        assert items == []

    def test_successful_paging_still_annotates_items(self):
        page = _ok_page([{"link": "https://sub.example.com/a"}] * 10)
        with patch.object(g.requests, "get", return_value=page):
            items, _ = _client()._get_search_results("myquery", max_results=10)
        assert len(items) == 10
        assert items[0]["search_query"] == "myquery"
        assert items[0]["domain"] == "example"
        assert items[0]["start_page"] == 1


class TestCallBudget:
    """#4 -- the budget was a nonlocal int mutated by 5 threads with lost updates."""

    def test_reserve_grants_up_to_limit(self):
        b = g.CallBudget(3)
        assert b.reserve(2) == 2
        assert b.reserve(2) == 1
        assert b.reserve(1) == 0
        assert b.remaining == 0

    def test_release_returns_capacity(self):
        b = g.CallBudget(2)
        b.reserve(2)
        b.release(1)
        assert b.remaining == 1

    def test_reserve_is_atomic_not_merely_lucky(self):
        """Deterministic: the read-modify-write must happen under the lock.

        A stress test alone is a poor guard here -- the GIL makes a short
        unlocked `self._used += n` win most of the time, so a racy
        implementation passes it by luck. This forces the interleaving instead:
        a second thread calls reserve() while the first is *inside* the
        critical section. With a real lock it blocks and the total is correct;
        without one it reads a stale count and both are granted.
        """
        b = g.CallBudget(1)
        entered = threading.Event()
        release = threading.Event()
        real_lock = b._lock

        class BlockingLock:
            """Signals on acquire, then holds until the test lets go."""
            def __enter__(self):
                real_lock.acquire()
                entered.set()
                release.wait(timeout=5)
                return self
            def __exit__(self, *exc):
                real_lock.release()
                return False

        b._lock = BlockingLock()
        first: list[int] = []
        t = threading.Thread(target=lambda: first.append(b.reserve(1)))
        t.start()
        assert entered.wait(timeout=5), "reserve() never entered its lock -- it is not synchronised"

        # The contender must not be able to reserve while the lock is held.
        b._lock = real_lock
        second: list[int] = []
        t2 = threading.Thread(target=lambda: second.append(b.reserve(1)))
        t2.start()
        t2.join(timeout=0.5)
        assert t2.is_alive(), "a second reserve() proceeded while the lock was held"

        release.set()
        t.join(timeout=5)
        t2.join(timeout=5)

        assert first == [1]
        assert second == [0], "budget of 1 granted twice"
        assert b.used == 1

    def test_never_exceeds_limit_under_concurrency(self):
        """Stress test, kept as a cheap backstop for egregious races."""
        b = g.CallBudget(50)
        with cf.ThreadPoolExecutor(max_workers=16) as ex:
            granted = sum(ex.map(lambda _: b.reserve(1), range(500)))
        assert granted == 50
        assert b.used == 50

    def test_paging_respects_shared_budget_across_threads(self):
        page = _ok_page([{"link": "https://e.com/a"}] * 10)
        b = g.CallBudget(20)
        c = _client()
        with patch.object(g.requests, "get", return_value=page):
            with cf.ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(
                    lambda i: c._get_search_results(f"q{i}", max_results=100, budget=b),
                    range(30),
                ))
        assert b.used == 20, f"budget overspent: {b.used}/20"
