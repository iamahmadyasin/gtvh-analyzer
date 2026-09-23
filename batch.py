"""
OpenAI Batch API client: the same `call_structured` contract as LLMClient,
at the Batch API's discounted price, with results within 24 hours instead
of immediately.

How it fits the pipeline without changing any stage code: every story is
analyzed at once, and `call_structured` only queues its request and waits.
Once every story is waiting (no new requests for a moment), the whole
queue is sent as one batch. So all stories' segmentation calls go in one
batch, then all their detection calls, then all their annotation calls:
three batches per run, each needing the previous one's results.

Results are written to the same checkpoints as the online client, so a
batch run and an online run of the same inputs share results. Each
submitted batch is recorded under `<checkpoint_dir>/batches/` until its
results are saved; if the process is stopped while waiting, re-running
the same command picks the batch up again instead of paying for it twice.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence, Type

from openai import APIConnectionError, APIStatusError
from openai.lib._parsing._completions import type_to_response_format_param
from pydantic import BaseModel, ValidationError

from llm import LLMClient, R, T, run_all

ENDPOINT = "/v1/chat/completions"
TERMINAL = {"completed", "failed", "expired", "cancelled"}


@dataclass
class _Queued:
    body: dict
    response_model: Type[BaseModel]
    futures: list[asyncio.Future] = field(default_factory=list)


class BatchLLMClient(LLMClient):
    def __init__(
        self,
        *args,
        poll_interval: float = 60.0,
        idle_wait: float = 0.5,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if self.checkpoint_dir is None:
            raise ValueError("Batch mode needs a checkpoint_dir to store results.")
        self.poll_interval = poll_interval
        self.idle_wait = idle_wait
        self.batch_dir = self.checkpoint_dir / "batches"
        self._queue: dict[str, _Queued] = {}
        self._flusher: asyncio.Task | None = None

    async def map(
        self,
        items: Sequence[R],
        fn: Callable[[R], Awaitable[T]],
        concurrency: int,
    ) -> list[T]:
        # Queue everything at once: a concurrency cap or a warm-up call
        # would split one stage into many batches, each a separate wait.
        return await run_all(items, fn, max(len(items), 1), warm_up=False)

    async def call_structured(self, system_prompt, user_message, response_model):
        messages = self._messages(system_prompt, user_message)
        checkpoint = self._checkpoint_path(messages, response_model)
        cached = self._load_checkpoint(checkpoint, response_model)
        if cached is not None:
            self.usage.checkpoint_hits += 1
            return cached

        key = checkpoint.stem  # also the batch custom_id
        if key not in self._queue:
            body = {
                "model": self.model,
                "messages": messages,
                "response_format": type_to_response_format_param(response_model),
                "prompt_cache_key": self._cache_key(messages),
            }
            if self.temperature is not None:
                body["temperature"] = self.temperature
            self._queue[key] = _Queued(body, response_model)
        future = asyncio.get_running_loop().create_future()
        self._queue[key].futures.append(future)
        if self._flusher is None or self._flusher.done():
            self._flusher = asyncio.create_task(self._flush_when_idle())
        return await future

    async def _flush_when_idle(self) -> None:
        while self._queue:
            # Nothing else in the pipeline does I/O in batch mode, so once
            # the queue stops growing every story is waiting on it.
            size = -1
            while len(self._queue) != size:
                size = len(self._queue)
                await asyncio.sleep(self.idle_wait)
            queued, self._queue = self._queue, {}
            try:
                await self._process(queued)
            except Exception as exc:  # noqa: BLE001
                for item in queued.values():
                    for future in item.futures:
                        if not future.done():
                            future.set_exception(exc)

    async def _process(self, queued: dict[str, _Queued]) -> None:
        results: dict[str, str | Exception] = {}

        # A batch from an interrupted run may already cover these requests.
        for record_path in sorted(self.batch_dir.glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if set(record["keys"]) & queued.keys():
                print(f"    resuming batch {record['id']}")
                results.update(await self._collect(record["id"]))
                record_path.unlink()

        todo = {k: v for k, v in queued.items() if k not in results}
        if todo:
            results.update(await self._submit_and_collect(todo))

        for key, item in queued.items():
            outcome = results.get(key, RuntimeError(f"batch returned no result for {key}"))
            if isinstance(outcome, str):
                try:
                    outcome = item.response_model.model_validate_json(outcome)
                except ValidationError as exc:
                    outcome = exc
            for future in item.futures:
                if isinstance(outcome, Exception):
                    future.set_exception(outcome)
                else:
                    future.set_result(outcome)

    async def _submit_and_collect(
        self, todo: dict[str, _Queued]
    ) -> dict[str, str | Exception]:
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps({"custom_id": key, "method": "POST", "url": ENDPOINT,
                        "body": item.body}, ensure_ascii=False)
            for key, item in todo.items()
        ]
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        upload = await self.client.files.create(
            file=("requests.jsonl", payload), purpose="batch"
        )
        batch = await self.client.batches.create(
            input_file_id=upload.id, endpoint=ENDPOINT, completion_window="24h"
        )
        record_path = self.batch_dir / f"{batch.id}.json"
        record_path.write_text(
            json.dumps({"id": batch.id, "keys": list(todo)}), encoding="utf-8"
        )
        print(f"    submitted batch {batch.id} ({len(todo)} requests)")
        results = await self._collect(batch.id)
        record_path.unlink()
        return results

    async def _collect(self, batch_id: str) -> dict[str, str | Exception]:
        """Wait for a batch to finish, checkpoint every successful result,
        and return raw JSON content (or an error) per custom_id."""
        started = time.monotonic()
        while True:
            try:
                batch = await self.client.batches.retrieve(batch_id)
            except (APIConnectionError, APIStatusError) as exc:
                if getattr(exc, "status_code", 500) < 500:
                    raise
                batch = None  # transient: try again next poll
            if batch is not None:
                counts = batch.request_counts
                done = f"{counts.completed + counts.failed}/{counts.total}" if counts else "?"
                if self.verbose:
                    minutes = (time.monotonic() - started) / 60
                    print(f"    batch {batch_id}: {batch.status} {done} ({minutes:.0f} min)")
                if batch.status in TERMINAL:
                    break
            await asyncio.sleep(self.poll_interval)

        if batch.status == "failed":
            errors = getattr(batch.errors, "data", None) or []
            detail = "; ".join(e.message or "" for e in errors) or "no details"
            raise RuntimeError(f"batch {batch_id} failed: {detail}")

        results: dict[str, str | Exception] = {}
        for file_id in (batch.output_file_id, batch.error_file_id):
            if not file_id:
                continue
            content = await self.client.files.content(file_id)
            for raw in content.text.splitlines():
                if raw.strip():
                    key, outcome = self._read_result(json.loads(raw))
                    results[key] = outcome
        if batch.status != "completed":
            print(f"    batch {batch_id} {batch.status}: kept {len(results)} results; "
                  f"re-run to retry the rest")
        return results

    def _read_result(self, line: dict) -> tuple[str, str | Exception]:
        key = line["custom_id"]
        response = line.get("response") or {}
        body = response.get("body") or {}
        if line.get("error") or response.get("status_code") != 200:
            error = line.get("error") or body.get("error") or response
            return key, RuntimeError(f"batch request failed: {error}")

        usage = body.get("usage") or {}
        self.usage.api_calls += 1
        self.usage.input_tokens += usage.get("prompt_tokens") or 0
        self.usage.output_tokens += usage.get("completion_tokens") or 0
        details = usage.get("prompt_tokens_details") or {}
        self.usage.cached_input_tokens += details.get("cached_tokens") or 0

        message = body["choices"][0]["message"]
        if not message.get("content"):
            return key, RuntimeError(
                f"Model returned no content. Refusal: {message.get('refusal')!r}"
            )
        path = self.checkpoint_dir / key[:2] / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(message["content"], encoding="utf-8")
        tmp.replace(path)
        return key, message["content"]
