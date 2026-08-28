"""Regression tests for the bugs found in the 2026-08-28 audit.

Each class is named for its audit item. These lock in behaviour that had no
coverage at the time the bug was introduced, which is why the bugs survived.
"""
import concurrent.futures as cf
import threading
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests as R

import src.search.google_search as g
from src.job_tracking.job_tracker import _redis_from_url
from src.pipeline.query_generator import QueryGenerator
from src.processing.annotations import Annotations, AnnotationType
from src.storage.s3 import S3StorageBackend
from types import SimpleNamespace


@pytest.fixture
def qg_settings():
    """Minimal settings for QueryGenerator: one template, one param set."""
    return SimpleNamespace(
        prompt_templates={"query": "Generate queries for: {input}"},
        generation_params={"query": {"temperature": 0.3, "max_tokens": 512}},
    )


@pytest.fixture
def ann_settings(tmp_path):
    """Crawl-policy settings pointed at tmp_path so nothing touches the real cache."""
    return SimpleNamespace(
        allowed_path=tmp_path / "allowed.txt",
        not_allowed_path=tmp_path / "not_allowed.txt",
        reasoning_path=tmp_path / "reasoning.jsonl",
        error_log_path=tmp_path / "malformed.log",
        sub_categories=[],
        prompt_templates={"crawlable_annotation": "Classify: {input}"},
        generation_params={"crawlable": {"temperature": 0}},
    )



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


class TestAudit01GoogleErrorPaths:
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


class TestAudit04CallBudget:
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


class TestAudit02NoLLMResponse:
    """#2 -- split_queries(None) raised AttributeError on the first pipeline step."""

    class _NullLLM:
        def chat_sync(self, prompts, params=None, **kw):
            return [None] * len(prompts)

    class _EmptyLLM:
        def chat_sync(self, prompts, params=None, **kw):
            return []

    def _qg(self, llm, settings):
        return QueryGenerator(llm, settings, lambda m, level="info": None)

    def test_none_response_raises_actionable_error(self, qg_settings):
        qg = self._qg(self._NullLLM(), qg_settings)
        with pytest.raises(RuntimeError, match="LLM_MODEL_NAME"):
            qg.generate_queries("x", mode="query", template_key="query")

    def test_empty_response_list_raises_too(self, qg_settings):
        qg = self._qg(self._EmptyLLM(), qg_settings)
        with pytest.raises(RuntimeError):
            qg.generate_queries("x", mode="query", template_key="query")

    def test_not_attribute_error(self, qg_settings):
        """The old failure mode, pinned so it cannot come back."""
        qg = self._qg(self._NullLLM(), qg_settings)
        with pytest.raises(Exception) as exc:
            qg.generate_queries("x", mode="query", template_key="query")
        assert not isinstance(exc.value, AttributeError)


class TestAudit05PartialBatchResponses:
    """#5 -- an empty first batch discarded every other batch's classifications."""

    class _FirstBatchEmptyLLM:
        def chat_sync(self, prompts, params=None, **kw):
            good = '{"domain": "good", "status": "ok"}'
            return [None] + [good] * (len(prompts) - 1)

    def test_later_batches_survive_an_empty_first_batch(self, ann_settings, tmp_path):
        ann_settings.allowed_path = tmp_path / "allowed.txt"
        ann_settings.not_allowed_path = tmp_path / "not_allowed.txt"
        ann_settings.reasoning_path = tmp_path / "reasoning.jsonl"
        ann_settings.error_log_path = tmp_path / "malformed.log"

        # 10 unlisted domains -> batches of 5 -> 2 prompts, the first empty.
        df = pd.DataFrame({"domain": [f"d{i}" for i in range(10)]})
        ann = Annotations(settings=ann_settings, llm=self._FirstBatchEmptyLLM(), input="topic")
        out = ann.apply(df, annotations=[AnnotationType.DONOTCRAWL])

        assert (tmp_path / "allowed.txt").exists(), \
            "the surviving batch's classification was discarded"
        assert "good" in (tmp_path / "allowed.txt").read_text()
        assert "crawlable" in out.columns

    def test_all_batches_empty_still_returns_df(self, ann_settings, tmp_path):
        ann_settings.allowed_path = tmp_path / "allowed.txt"
        ann_settings.not_allowed_path = tmp_path / "not_allowed.txt"
        ann_settings.reasoning_path = tmp_path / "reasoning.jsonl"
        ann_settings.error_log_path = tmp_path / "malformed.log"

        class AllEmpty:
            def chat_sync(self, prompts, params=None, **kw):
                return [None] * len(prompts)

        df = pd.DataFrame({"domain": ["a", "b"]})
        ann = Annotations(settings=ann_settings, llm=AllEmpty(), input="t")
        out = ann.apply(df, annotations=[AnnotationType.DONOTCRAWL])
        assert len(out) == 2
        assert not (tmp_path / "allowed.txt").exists()


class TestAudit07RedisUrl:
    """#7 -- hand-parsing the URL dropped credentials and TLS."""

    def test_plain_url_unchanged(self):
        kw = _redis_from_url("redis://localhost:6379/0").connection_pool.connection_kwargs
        assert (kw["host"], kw["port"], kw["db"]) == ("localhost", 6379, 0)

    def test_password_is_honoured(self):
        kw = _redis_from_url("redis://:secret@h:6380/2").connection_pool.connection_kwargs
        assert kw["password"] == "secret"
        assert (kw["host"], kw["port"], kw["db"]) == ("h", 6380, 2)

    def test_username_and_password_honoured(self):
        kw = _redis_from_url("redis://user:pw@h/1").connection_pool.connection_kwargs
        assert (kw["username"], kw["password"]) == ("user", "pw")

    def test_rediss_uses_tls_connection(self):
        pool = _redis_from_url("rediss://h/0").connection_pool
        assert "ssl" in pool.connection_class.__name__.lower()


class TestAudit03S3Bucket:
    """#3 -- STORAGE_BUCKET was accepted and documented but never read."""

    def _backend(self, bucket):
        with patch("src.storage.s3.S3FileSystem"), patch("src.storage.s3.boto3.client"):
            return S3StorageBackend("ak", "sk", "https://s3.example", "us-east-1", bucket)

    def test_configured_bucket_is_used(self):
        b = self._backend("my-bucket")
        assert b._split_bucket_key("results/run/x.zip") == ("my-bucket", "results/run/x.zip")

    def test_bucket_qualified_path_is_not_double_prefixed(self):
        b = self._backend("my-bucket")
        assert b._split_bucket_key("my-bucket/run/x.zip") == ("my-bucket", "run/x.zip")

    def test_falls_back_to_first_segment_when_unset(self):
        """Historical behaviour, preserved: pyarrow paths are bucket-qualified."""
        b = self._backend("")
        assert b._split_bucket_key("results/run/x.zip") == ("results", "run/x.zip")

    def test_presigned_url_uses_configured_bucket(self):
        b = self._backend("my-bucket")
        b.generate_presigned_url("results/run/x.zip", expires_in=60)
        b._boto_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "results/run/x.zip"},
            ExpiresIn=60,
        )

    def test_presigned_url_without_configured_bucket(self):
        b = self._backend("")
        b.generate_presigned_url("results/run/x.zip")
        _, kwargs = b._boto_client.generate_presigned_url.call_args
        assert kwargs["Params"] == {"Bucket": "results", "Key": "run/x.zip"}
