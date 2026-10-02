"""
OpenAI client: a thin async wrapper around OpenAI's structured-output API.

The Claude client is llm_claude.py; what both share (checkpoints, usage,
run_all) is in llm_base.py. Everything downstream depends only on
`call_structured(...) -> PydanticModel`.

Uses `client.chat.completions.parse()` — the stable structured-outputs
path. (This method used to live under `client.beta.*`; it has since
graduated out of beta.)

Handles rate limits (HTTP 429) with automatic retry and exponential
backoff, honoring the `retry-after` header when the API supplies one.

Two ways of not paying twice:

- Prompt caching (provider side). OpenAI automatically bills a repeated
  prompt prefix of 1024+ tokens at the cached-input rate. Stages put
  everything shared between calls (system prompt, then the full story)
  first and the call-specific part last, and every call is tagged with a
  `prompt_cache_key` derived from that shared prefix so the requests are
  routed to the same cache.
- Checkpoints (local). Each successful response is saved under
  `checkpoint_dir`, keyed by a hash of everything that determines it
  (model, temperature, messages, response schema). Re-running after a
  crash, or after editing only a later stage's prompt, reuses every call
  whose inputs are unchanged.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path
from typing import Awaitable, Callable, Sequence, Type

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, RateLimitError

from llm_base import BaseLLMClient, R, T, Usage, _sha256, run_all

# Re-exported: other modules import these from here.
__all__ = ["LLMClient", "Usage", "run_all", "R", "T"]


class LLMClient(BaseLLMClient):
    """OpenAI (Chat Completions structured outputs)."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        temperature: float | None = 0.0,
        max_retries: int = 6,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        verbose: bool = True,
        checkpoint_dir: Path | None = None,
        fresh: bool = False,
    ):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it, or put it in a .env file."
            )
        super().__init__(model, temperature, verbose, checkpoint_dir, fresh)
        self.client = AsyncOpenAI(api_key=key, max_retries=0)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

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

    def _record_usage(self, completion) -> None:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        self.usage.input_tokens += usage.prompt_tokens or 0
        self.usage.output_tokens += usage.completion_tokens or 0
        details = getattr(usage, "prompt_tokens_details", None)
        self.usage.cached_input_tokens += getattr(details, "cached_tokens", 0) or 0

    async def call_structured(
        self,
        system_prompt: str,
        user_message: str | Sequence[str],
        response_model: Type[T],
    ) -> T:
        """`user_message` may be a list: put the parts shared across calls
        (e.g. the full story) first and the call-specific part last, so the
        shared prefix can be served from the provider's prompt cache."""
        messages = self._messages(system_prompt, user_message)
        checkpoint = self._checkpoint_path(messages, response_model)
        cached = self._load_checkpoint(checkpoint, response_model)
        if cached is not None:
            self.usage.checkpoint_hits += 1
            return cached

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "response_format": response_model,
            # Routes calls sharing a prefix to the same cache. Passed via
            # extra_body so older SDK versions without the param still work.
            "extra_body": {"prompt_cache_key": self._cache_key(messages)},
        }
        # Some models only accept their default temperature; omit when None.
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        async def _call():
            completion = await self.client.chat.completions.parse(**kwargs)
            self.usage.api_calls += 1
            self._record_usage(completion)
            message = completion.choices[0].message
            if message.parsed is None:
                raise RuntimeError(
                    f"Model returned no parsed content for "
                    f"{response_model.__name__}. Refusal: {message.refusal!r}"
                )
            return message.parsed

        result = await self._with_retries(_call)
        self._save_checkpoint(checkpoint, result)
        return result

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        """Embedding vectors for `texts`, in order. Checkpointed like
        structured calls, so re-running normalization is free."""
        texts = list(texts)
        if not texts:
            return []
        path = None
        if self.checkpoint_dir is not None:
            key = _sha256({"embed_model": model, "texts": texts})
            path = self.checkpoint_dir / key[:2] / f"{key}.json"
            if not self.fresh and path.exists():
                try:
                    self.usage.checkpoint_hits += 1
                    return json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    self.usage.checkpoint_hits -= 1  # unreadable: recompute

        async def _call():
            response = await self.client.embeddings.create(model=model, input=texts)
            self.usage.api_calls += 1
            self.usage.input_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
            return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]

        vectors = await self._with_retries(_call)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(vectors), encoding="utf-8")
            os.replace(tmp, path)
        return vectors

    async def _with_retries(self, call: Callable[[], Awaitable[R]]) -> R:
        """Run one API request, retrying rate limits (honoring retry-after)
        and transient server or connection errors with backoff."""
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                return await call()

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
