import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.llm.generator import LLMClient
import httpx
import logging
import openai
from types import SimpleNamespace
from src.llm.generator import NON_RETRYABLE_ERRORS


class TestLLMClientInit:
    def test_stores_model_and_url(self):
        with patch("src.llm.generator.AsyncOpenAI"):
            gen = LLMClient("test-model", "http://example.com/v1", "fake-key")
            assert gen.model == "test-model"
            assert gen.base_url == "http://example.com/v1"

    def test_creates_openai_client(self):
        with patch("src.llm.generator.AsyncOpenAI") as mock_client:
            gen = LLMClient("model", "http://url/v1", "my-key")
            mock_client.assert_called_once_with(
                api_key="my-key",
                base_url="http://url/v1",
                default_headers=None,
            )

    def test_passes_extra_headers(self):
        with patch("src.llm.generator.AsyncOpenAI") as mock_client:
            headers = {"X-Custom-Auth": "test-secret"}
            gen = LLMClient("model", "http://url/v1", "my-key", extra_headers=headers)
            mock_client.assert_called_once_with(
                api_key="my-key",
                base_url="http://url/v1",
                default_headers=headers,
            )


class TestLLMClientChat:
    @pytest.fixture
    def generator(self):
        with patch("src.llm.generator.AsyncOpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            gen = LLMClient("model", "http://url/v1", "key")
            gen.client = mock_client
            return gen

    def test_single_prompt_success(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response text"

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        results = asyncio.run(generator.chat(["test prompt"], show_progress=False))
        assert results == ["response text"]

    def test_multiple_prompts(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        results = asyncio.run(generator.chat(["p1", "p2", "p3"], show_progress=False))
        assert len(results) == 3
        assert all(r == "response" for r in results)

    def test_none_response_content(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        results = asyncio.run(generator.chat(["prompt"], show_progress=False))
        assert results == [None]

    def test_empty_response_content(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        results = asyncio.run(generator.chat(["prompt"], show_progress=False))
        assert results == [None]

    def test_retry_on_failure_then_success(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "success"

        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("temporary error")
            return mock_response

        generator.client.chat.completions.create = side_effect

        async def noop_sleep(t):
            pass

        with patch("asyncio.sleep", noop_sleep):
            results = asyncio.run(generator.chat(["prompt"], show_progress=False))
        assert results == ["success"]
        assert call_count == 3

    def test_all_retries_exhausted(self, generator):
        generator.client.chat.completions.create = AsyncMock(
            side_effect=Exception("permanent error")
        )

        async def noop_sleep(t):
            pass

        with patch("asyncio.sleep", noop_sleep):
            results = asyncio.run(generator.chat(["prompt"], show_progress=False))
        assert results == [None]

    def test_respects_params(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        params = {"temperature": 0.5, "max_tokens": 100}
        asyncio.run(generator.chat(["prompt"], params=params, show_progress=False))

        call_kwargs = generator.client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100

    def test_unicode_cleaned(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "  text with spaces  "

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        results = asyncio.run(generator.chat(["prompt"], show_progress=False))
        assert results == ["text with spaces"]

    def test_concurrency_respected(self, generator):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"

        generator.client.chat.completions.create = AsyncMock(return_value=mock_response)

        prompts = [f"prompt_{i}" for i in range(20)]
        results = asyncio.run(generator.chat(prompts, concurrency=2, show_progress=False))
        assert len(results) == 20


def _openai_error(cls, status):
    response = httpx.Response(status, request=httpx.Request("POST", "http://x/v1/chat"))
    return cls("nope", response=response, body=None)


class TestNonRetryableLLMErrors:
    """Every exception was retried -- 10 attempts backing off to 27s -- including
    401/403/404, so a typo in LLM_MODEL_NAME took ~4 minutes per prompt to fail."""

    @pytest.mark.parametrize("cls,status", [
        (openai.AuthenticationError, 401),
        (openai.PermissionDeniedError, 403),
        (openai.NotFoundError, 404),
        (openai.BadRequestError, 400),
    ])
    def test_classified_as_non_retryable(self, cls, status):
        assert isinstance(_openai_error(cls, status), NON_RETRYABLE_ERRORS)

    def test_rate_limit_is_still_retryable(self):
        """429 must keep retrying -- that is what the backoff is for."""
        assert not isinstance(_openai_error(openai.RateLimitError, 429), NON_RETRYABLE_ERRORS)

    def test_a_bad_key_is_not_retried(self):
        """One call, not ten, and no backoff sleep."""
        from src.llm.generator import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.model = "m"
        client.logger = logging.getLogger("test-llm-retry")
        create = MagicMock(side_effect=_openai_error(openai.AuthenticationError, 401))
        client.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

        import asyncio

        with patch("asyncio.sleep") as slept:
            result = asyncio.run(client.chat(["p"], show_progress=False))

        assert result == [None]
        assert create.call_count == 1, f"retried {create.call_count} times"
        slept.assert_not_called()
