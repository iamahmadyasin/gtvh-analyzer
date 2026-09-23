"""
Thin async wrapper around OpenAI's structured-output API.

Swap this file to switch providers. Everything downstream depends only on
`LLMClient.call_structured(...) -> PydanticModel`.

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
import hashlib
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Sequence, Type, TypeVar

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


def _sha256(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class Usage:
    api_calls: int = 0
    checkpoint_hits: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def summary(self) -> str:
        return (
            f"api_calls={self.api_calls} from_checkpoint={self.checkpoint_hits} "
            f"input_tokens={self.input_tokens} "
            f"(cached={self.cached_input_tokens}) "
            f"output_tokens={self.output_tokens}"
        )


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
        checkpoint_dir: Path | None = None,
        fresh: bool = False,
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
        self.checkpoint_dir = checkpoint_dir
        self.fresh = fresh  # ignore existing checkpoints (still writes new ones)
        self.usage = Usage()

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

    def _checkpoint_path(
        self, messages: list[dict], response_model: Type[BaseModel]
    ) -> Path | None:
        if self.checkpoint_dir is None:
            return None
        key = _sha256({
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
            "schema": response_model.model_json_schema(),
        })
        return self.checkpoint_dir / key[:2] / f"{key}.json"

    def _load_checkpoint(self, path: Path | None, response_model: Type[T]) -> T | None:
        if path is None or self.fresh or not path.exists():
            return None
        try:
            return response_model.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # unreadable or stale: just recompute

    @staticmethod
    def _save_checkpoint(path: Path | None, result: BaseModel) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(result.model_dump_json(), encoding="utf-8")
        os.replace(tmp, path)  # atomic: an interrupted write never leaves half a file

    def _record_usage(self, completion) -> None:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        self.usage.input_tokens += usage.prompt_tokens or 0
        self.usage.output_tokens += usage.completion_tokens or 0
        details = getattr(usage, "prompt_tokens_details", None)
        self.usage.cached_input_tokens += getattr(details, "cached_tokens", 0) or 0

    @staticmethod
    def _messages(system_prompt: str, user_message: str | Sequence[str]) -> list[dict]:
        parts = [user_message] if isinstance(user_message, str) else list(user_message)
        return [{"role": "system", "content": system_prompt}] + [
            {"role": "user", "content": part} for part in parts
        ]

    @staticmethod
    def _cache_key(messages: list[dict]) -> str:
        """Same for every call sharing everything but the last message."""
        return _sha256(messages[:-1])[:32]

    async def map(
        self,
        items: Sequence[R],
        fn: Callable[[R], Awaitable[T]],
        concurrency: int,
    ) -> list[T]:
        """Run one stage's calls. See `run_all`."""
        return await run_all(items, fn, concurrency)

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

        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                completion = await self.client.chat.completions.parse(**kwargs)
                self.usage.api_calls += 1
                self._record_usage(completion)
                message = completion.choices[0].message
                if message.parsed is None:
                    raise RuntimeError(
                        f"Model returned no parsed content for "
                        f"{response_model.__name__}. Refusal: {message.refusal!r}"
                    )
                self._save_checkpoint(checkpoint, message.parsed)
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


async def run_all(
    items: Sequence[R],
    fn: Callable[[R], Awaitable[T]],
    concurrency: int,
    warm_up: bool = True,
) -> list[T]:
    """Run `fn` over `items` with a concurrency cap.

    With `warm_up`, the first item runs alone so its prompt prefix is
    cached before the rest start; parallel requests sent before any
    response would all miss the cache. Every call runs to completion even if some fail, so each
    success is checkpointed; failures are then raised together and a
    re-run only repeats the calls that failed.
    """
    if not items:
        return []
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(item: R) -> T:
        async with sem:
            return await fn(item)

    first = 1 if warm_up else 0
    results = await asyncio.gather(
        *[_guarded(item) for item in items[:first]], return_exceptions=True
    )
    results += await asyncio.gather(
        *[_guarded(item) for item in items[first:]], return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        raise RuntimeError(
            f"{len(errors)} of {len(items)} calls failed; completed calls are "
            f"checkpointed, so re-running resumes from here. "
            f"First error: {errors[0]!r}"
        ) from errors[0]
    return results
