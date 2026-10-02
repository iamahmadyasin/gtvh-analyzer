"""
Batch-mode plumbing shared by the OpenAI and Claude batch clients.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence, Type

from pydantic import BaseModel, ValidationError

from llm_base import R, T, run_all


@dataclass
class _Queued:
    body: dict
    response_model: Type[BaseModel]
    futures: list[asyncio.Future] = field(default_factory=list)


class BatchQueueMixin:
    def _init_batch(self, poll_interval: float, idle_wait: float) -> None:
        if self.checkpoint_dir is None:
            raise ValueError("Batch mode needs a checkpoint_dir to store results.")
        self.poll_interval = poll_interval
        self.idle_wait = idle_wait
        self.batch_dir = self.checkpoint_dir / "batches"
        self._queue: dict[str, _Queued] = {}
        self._flusher: asyncio.Task | None = None

    # ---------- provider hooks ----------

    def _batch_body(self, messages: list[dict], response_model: Type[BaseModel]) -> dict:
        raise NotImplementedError

    async def _submit(self, todo: dict[str, _Queued]) -> str:
        raise NotImplementedError

    async def _collect(self, batch_id: str) -> dict[str, str | Exception]:
        raise NotImplementedError

    # ---------- queueing ----------

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
            self._queue[key] = _Queued(self._batch_body(messages, response_model), response_model)
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

    async def _submit_and_collect(self, todo: dict[str, _Queued]) -> dict[str, str | Exception]:
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        batch_id = await self._submit(todo)
        record_path = self.batch_dir / f"{batch_id}.json"
        record_path.write_text(json.dumps({"id": batch_id, "keys": list(todo)}), encoding="utf-8")
        print(f"    submitted batch {batch_id} ({len(todo)} requests)")
        results = await self._collect(batch_id)
        record_path.unlink()
        return results

    def _checkpoint_raw(self, key: str, text: str) -> None:
        self._save_checkpoint(self.checkpoint_dir / key[:2] / f"{key}.json", text)
