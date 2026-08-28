import asyncio
from tqdm.asyncio import tqdm
from typing import List, Dict, Any
from openai import (
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)

# Retrying these never helps: a bad key, a revoked key, a wrong model name or a
# malformed request returns the same answer on attempt 10 as on attempt 1. They
# used to be retried like any other error -- 10 attempts backing off to 27s, so
# roughly four minutes per prompt -- which is why a typo in LLM_MODEL_NAME took
# hours to surface across a run instead of failing immediately.
NON_RETRYABLE_ERRORS = (
    AuthenticationError,     # 401 - bad or missing key
    PermissionDeniedError,   # 403 - key lacks access
    NotFoundError,           # 404 - unknown model or endpoint path
    BadRequestError,         # 400 - malformed request or unsupported params
)
from src.processing import utils

try:
    import nest_asyncio
    _nest_asyncio_available = True
except ImportError:
    _nest_asyncio_available = False


class LLMClient:
    """
    An asynchronous wrapper for interacting with any OpenAI-compatible API endpoint.

    Attributes:
        model (str): Name of the target model
        base_url (str): Base URL for API endpoint
        client: AsyncOpenAI instance configured with credentials and endpoint
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        extra_headers: dict | None = None,
    ):
        self.model = model
        self.base_url = base_url

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            default_headers=extra_headers or None,
        )

        self.logger = utils.get_default_logger()

    async def chat(
        self,
        prompts: List[str],
        concurrency: int = 5,
        params: Dict[str, Any] | None = None,
        show_progress: bool = True,
    ) -> List[str]:
        """
        Process multiple prompts concurrently with retry logic.
        """
        params = params or {}

        semaphore = asyncio.Semaphore(concurrency)

        async def process_prompt(prompt: str, index: int):
            max_retries = 10

            async with semaphore:
                for attempt in range(1, max_retries + 1):
                    try:
                        response = await self.client.chat.completions.create(
                            model=self.model,
                            messages=[{"role": "user", "content": prompt}],
                            **params
                        )
                        result = response.choices[0].message.content
                        if not result:
                            return None
                        result = utils.clean_unicode(result).strip()
                        return result

                    except NON_RETRYABLE_ERRORS as e:
                        # Fail on the first attempt and say what to check: the
                        # caller (QueryGenerator) turns a None into an actionable
                        # error, but only after every prompt has burned its
                        # retries, which is the slow part.
                        self.logger.error(
                            f"{type(e).__name__} from the LLM endpoint for prompt {index}: {e}. "
                            "Not retrying -- check LLM_API_KEY, LLM_BASE_URL and LLM_MODEL_NAME."
                        )
                        return None

                    except Exception as e:
                        error_msg = f"Attempt {attempt} failed for prompt {index}: {str(e)}"
                        self.logger.error(error_msg)

                        wait_time = min(3 * attempt, 27)

                        if attempt < max_retries:
                            await asyncio.sleep(wait_time)
                        else:
                            self.logger.warning(f"None llm response for prompt: {prompt}")
                            return None

        tasks = [process_prompt(prompt, i) for i, prompt in enumerate(prompts)]
        if show_progress == True:
            results = await tqdm.gather(*tasks, mininterval=10)
        else:
            results = await asyncio.gather(*tasks)

        return results

    def chat_sync(
        self,
        prompts: List[str],
        concurrency: int = 5,
        params: Dict[str, Any] | None = None,
        show_progress: bool = True,
    ) -> List[str]:
        """
        Synchronous wrapper around chat() that handles nested event loops.
        """
        if _nest_asyncio_available:
            nest_asyncio.apply()
        return asyncio.run(self.chat(prompts, concurrency=concurrency, params=params, show_progress=show_progress))
