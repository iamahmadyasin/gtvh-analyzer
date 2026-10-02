"""
Provider-neutral parts of the model clients.
The provider clients subclass implement the actual API calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Sequence, Type, TypeVar

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
    input_tokens: int = 0         # all input tokens, cached ones included
    cached_input_tokens: int = 0  # the part served from the provider's cache
    output_tokens: int = 0

    def summary(self) -> str:
        return (
            f"api_calls={self.api_calls} from_checkpoint={self.checkpoint_hits} "
            f"input_tokens={self.input_tokens} "
            f"(cached={self.cached_input_tokens}) "
            f"output_tokens={self.output_tokens}"
        )


class BaseLLMClient:
    """Shared state and helpers; subclasses implement call_structured."""

    def __init__(
        self,
        model: str,
        temperature: float | None = None,
        verbose: bool = True,
        checkpoint_dir: Path | None = None,
        fresh: bool = False,
    ):
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        self.checkpoint_dir = checkpoint_dir
        self.fresh = fresh  # ignore existing checkpoints (still writes new ones)
        self.usage = Usage()

    # ---------- checkpoints ----------

    def _checkpoint_settings(self) -> dict:
        """Settings besides the messages that change the response. Part of
        every checkpoint key, so changing one re-runs the affected calls."""
        return {"model": self.model, "temperature": self.temperature}

    def _checkpoint_path(
        self, messages: list[dict], response_model: Type[BaseModel]
    ) -> Path | None:
        if self.checkpoint_dir is None:
            return None
        key = _sha256({
            **self._checkpoint_settings(),
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
    def _save_checkpoint(path: Path | None, result: BaseModel | str) -> None:
        """Write a parsed result (or its raw JSON text) atomically."""
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        text = result if isinstance(result, str) else result.model_dump_json()
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic: an interrupted write never leaves half a file

    # ---------- messages ----------

    @staticmethod
    def _messages(system_prompt: str, user_message: str | Sequence[str]) -> list[dict]:
        """Provider-neutral message list: the system prompt, then each part
        of the user message in order (shared parts first, the call-specific
        part last). Also the input to checkpoint keys."""
        parts = [user_message] if isinstance(user_message, str) else list(user_message)
        return [{"role": "system", "content": system_prompt}] + [
            {"role": "user", "content": part} for part in parts
        ]

    @staticmethod
    def _cache_key(messages: list[dict]) -> str:
        """Same for every call sharing everything but the last message."""
        return _sha256(messages[:-1])[:32]

    # ---------- interface ----------

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
        raise NotImplementedError

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        """Embedding vectors for `texts`. Providers without an embeddings API
        raise, and normalization falls back to string similarity."""
        raise NotImplementedError(f"{type(self).__name__} has no embeddings API")


async def run_all(
    items: Sequence[R],
    fn: Callable[[R], Awaitable[T]],
    concurrency: int,
    warm_up: bool = True,
) -> list[T]:
    """Run `fn` over `items` with a concurrency cap.

    With `warm_up`, the first item runs alone so its prompt prefix is
    cached before the rest start; parallel requests sent before any
    response would all miss the cache. Every call runs to completion even
    if some fail, so each success is checkpointed; failures are then
    raised together and a re-run only repeats the calls that failed.
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
