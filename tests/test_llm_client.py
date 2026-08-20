import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.llm.generator import LLMClient


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
