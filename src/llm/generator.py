import asyncio
from tqdm.asyncio import tqdm
from typing import List, Dict, Any
from openai import AsyncOpenAI

class LLMGenerator:
    """
    An asynchronous wrapper class for interacting with a custom model API endpoint.
    
    Attributes:
        model (str): Name of the target model
        base_url (str): Base URL for API endpoint
        api_key (str): Authentication key for the service
        client: AsyncOpenAI instance configured with credentials and endpoint
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str
    ):
        """Initialize model client with authentication credentials."""
        self.model = model
        self.base_url = base_url
        
        # Create OpenAI client with authentication headers
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            default_headers={'LLM_API_KEY': api_key}
        )

    async def chat(
        self,
        prompts: List[str],
        concurrency: int = 5,
        params: Dict[str, Any] | None = None,
        show_progress: bool = True,
    ) -> List[str]:
        """
        Process multiple prompts concurrently with retry logic.
        
        Args:
            prompts: List of text inputs to process
            concurrency: Maximum number of parallel requests
            params: Additional parameters for API calls
            
        Returns:
            List[str]: Model responses corresponding to input order
                (None where errors occurred)
        """
        params = params or {}
        
        semaphore = asyncio.Semaphore(concurrency)

        # Process individual prompt with retry logic
        async def process_prompt(prompt: str, index: int):
            # Exponential backoff parameters
            max_retries = 10
            
            async with semaphore:
                for attempt in range(1, max_retries + 1):
                    try:
                        response = await self.client.chat.completions.create(
                            model=self.model,
                            messages=[{"role": "user", "content": prompt}],
                            **params
                        )
                        return response.choices[0].message.content.strip()
                    
                    except Exception as e:
                        error_msg = f"Attempt {attempt} failed for prompt {index}: {str(e)}"
                        print(error_msg)
                        
                        # Exponential backoff delay capped at 27 seconds
                        wait_time = min(3 * attempt, 27)
                        
                        if attempt < max_retries:
                            await asyncio.sleep(wait_time)
                        else:
                            return None

        # Create tasks preserving input order
        tasks = [process_prompt(prompt, i) for i, prompt in enumerate(prompts)]
        if show_progress == True:
            results = await tqdm.gather(*tasks, mininterval=10)
        else:
            results = await asyncio.gather(*tasks)
        
        return results