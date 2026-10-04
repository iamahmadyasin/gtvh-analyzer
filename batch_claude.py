"""
Batch clients · Claude
Sends a stage as one Claude message batch: half the price, results within 24
hours.

Reads:   queued requests from batch_base.py
Writes:  checkpointed responses
"""

from __future__ import annotations

import asyncio
import time
from typing import Type

import anthropic
from anthropic.lib._parse._transform import transform_schema 
from pydantic import BaseModel

from batch_base import BatchQueueMixin
from llm_claude import ClaudeClient


class ClaudeBatchClient(BatchQueueMixin, ClaudeClient):
    def __init__(self, *args, poll_interval: float = 60.0, idle_wait: float = 0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_batch(poll_interval, idle_wait)

    def _batch_body(self, messages: list[dict], response_model: Type[BaseModel]) -> dict:
        params = self._request_params(messages)
        params.setdefault("output_config", {})["format"] = {
            "type": "json_schema",
            "schema": transform_schema(response_model.model_json_schema()),
        }
        return params

    async def _submit(self, todo) -> str:
        batch = await self.client.messages.batches.create(
            requests=[{"custom_id": key, "params": item.body} for key, item in todo.items()]
        )
        return batch.id

    async def _collect(self, batch_id: str) -> dict[str, str | Exception]:
        """Waits for the batch to end, checkpoints each success, and returns raw
        JSON or an error per custom_id."""
        started = time.monotonic()
        while True:
            try:
                batch = await self.client.messages.batches.retrieve(batch_id)
            except (anthropic.APIConnectionError, anthropic.InternalServerError):
                batch = None  # transient: try again next poll
            if batch is not None:
                c = batch.request_counts
                if self.verbose:
                    minutes = (time.monotonic() - started) / 60
                    print(f"    batch {batch_id}: {batch.processing_status} "
                          f"{c.succeeded + c.errored + c.canceled + c.expired}/"
                          f"{c.processing + c.succeeded + c.errored + c.canceled + c.expired} "
                          f"({minutes:.0f} min)")
                if batch.processing_status == "ended":
                    break
            await asyncio.sleep(self.poll_interval)

        results: dict[str, str | Exception] = {}
        async for entry in await self.client.messages.batches.results(batch_id):
            key, outcome = entry.custom_id, entry.result
            if outcome.type != "succeeded":
                detail = getattr(getattr(outcome, "error", None), "error", None) or outcome.type
                results[key] = RuntimeError(f"batch request {outcome.type}: {detail}")
                continue
            message = outcome.message
            self._record_usage(message.usage)
            try:
                self._check_stop(message, f"batch request {key[:8]}")
            except RuntimeError as exc:
                results[key] = exc
                continue
            text = next((b.text for b in message.content if b.type == "text"), None)
            if not text:
                results[key] = RuntimeError("Claude returned no content")
                continue
            self._checkpoint_raw(key, text)
            results[key] = text
        failed = sum(isinstance(v, Exception) for v in results.values())
        if failed:
            print(f"    batch {batch_id}: {failed} request(s) failed; re-run to retry them")
        return results
