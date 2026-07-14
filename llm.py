"""
Thin async wrapper around OpenAI's structured-output API.

Swap this file to switch providers. Everything downstream depends only on
`LLMClient.call_structured(...) -> PydanticModel`.

Uses `client.chat.completions.parse()` — the stable structured-outputs
path. (This method used to live under `client.beta.*`; it has since
graduated out of beta.)

Handles rate limits (HTTP 429) with automatic retry and exponential
backoff, honoring the `retry-after` header when the API supplies one.
"""

from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path
from typing import Type, TypeVar

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from prompts/. `name` is the stem (no extension)."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


class LLMClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        temperature: float | None = 0.0,
        max_retries: int = 6,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        verbose: bool = True,
    ):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it, or put it in a .env file."
            )
        self.client = AsyncOpenAI(api_key=key, max_retries=0)
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.verbose = verbose

    def _retry_after(self, exc: Exception) -> float | None:
        response = getattr(exc, "response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        for key in ("retry-after-ms", "retry-after"):
            raw = headers.get(key)
            if raw:
                try:
                    value = float(raw)
                    return value / 1000.0 if key.endswith("-ms") else value
                except ValueError:
                    continue
        return None

    async def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_model: Type[T],
    ) -> T:
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "response_format": response_model,
        }
        # Some models only accept their default temperature; omit when None.
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                completion = await self.client.chat.completions.parse(**kwargs)
                message = completion.choices[0].message
                if message.parsed is None:
                    raise RuntimeError(
                        f"Model returned no parsed content for "
                        f"{response_model.__name__}. Refusal: {message.refusal!r}"
                    )
                return message.parsed

            except RateLimitError as exc:
                last_exc = exc
                suggested = self._retry_after(exc)
                delay = suggested if suggested is not None else min(
                    self.base_delay * (2 ** attempt), self.max_delay
                )
                delay += random.uniform(0, 0.5)  # jitter, avoid thundering herd
                if self.verbose:
                    print(
                        f"    rate limited — waiting {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                await asyncio.sleep(delay)

            except (APIConnectionError, APIStatusError) as exc:
                # Retry 5xx and connection blips; re-raise real client errors
                # (400 bad request, 401 auth, content filter, etc.).
                status = getattr(exc, "status_code", None)
                if status is not None and status < 500:
                    raise
                last_exc = exc
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                delay += random.uniform(0, 0.5)
                if self.verbose:
                    print(
                        f"    transient error ({status}) — retrying in "
                        f"{delay:.1f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Failed after {self.max_retries} attempts. Last error: {last_exc}"
        ) from last_exc
