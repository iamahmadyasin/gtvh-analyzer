"""
Model clients · Shared base
Checkpoints, usage counts and the concurrency runner used by both providers.

Reads:   messages from the stages, output/.checkpoints/
Writes:  output/.checkpoints/
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
        self.fresh = fresh  # skip saved checkpoints, but still save new ones
        self.usage = Usage()

    def _checkpoint_settings(self) -> dict:
        """Settings that change the answer; changing one re-runs the affected calls."""
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
            return None  # unreadable or out of date: recompute

    @staticmethod
    def _save_checkpoint(path: Path | None, result: BaseModel | str) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        text = result if isinstance(result, str) else result.model_dump_json()
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic, so an interrupted run never leaves half a file

    @staticmethod
    def _messages(system_prompt: str, user_message: str | Sequence[str]) -> list[dict]:
        """System prompt, then each user part in order. Checkpoint keys are built
        from this list."""
        parts = [user_message] if isinstance(user_message, str) else list(user_message)
        return [{"role": "system", "content": system_prompt}] + [
            {"role": "user", "content": part} for part in parts
        ]

    @staticmethod
    def _cache_key(messages: list[dict]) -> str:
        """Identical for calls that differ only in their last message."""
        return _sha256(messages[:-1])[:32]

    async def map(
        self,
        items: Sequence[R],
        fn: Callable[[R], Awaitable[T]],
        concurrency: int,
    ) -> list[T]:
        """Batch clients override this to queue a whole stage at once."""
        return await run_all(items, fn, concurrency)

    async def call_structured(
        self,
        system_prompt: str,
        user_message: str | Sequence[str],
        response_model: Type[T],
    ) -> T:
        raise NotImplementedError

    async def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        """Providers without an embeddings API raise here, and normalization falls
        back to string similarity."""
        raise NotImplementedError(f"{type(self).__name__} has no embeddings API")


async def run_all(
    items: Sequence[R],
    fn: Callable[[R], Awaitable[T]],
    concurrency: int,
    warm_up: bool = True,
) -> list[T]:
    """Runs fn over items with a concurrency cap. Every call finishes before
    failures are raised, so each success is checkpointed and a re-run repeats
    only the calls that failed."""
    if not items:
        return []
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(item: R) -> T:
        async with sem:
            return await fn(item)

    # The first call goes alone, so its prompt prefix is cached before the
    # others are sent; requests sent together would all miss the cache.
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
