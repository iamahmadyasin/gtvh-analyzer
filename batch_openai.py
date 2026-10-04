"""
Batch clients · OpenAI
Sends a stage as one OpenAI batch: half the price, results within 24 hours.

Reads:   queued requests from batch_base.py
Writes:  checkpointed responses
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Type

from openai import APIConnectionError, APIStatusError
from openai.lib._parsing._completions import type_to_response_format_param
from pydantic import BaseModel

from batch_base import BatchQueueMixin
from llm_openai import LLMClient

ENDPOINT = "/v1/chat/completions"
TERMINAL = {"completed", "failed", "expired", "cancelled"}


class BatchLLMClient(BatchQueueMixin, LLMClient):
    def __init__(self, *args, poll_interval: float = 60.0, idle_wait: float = 0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_batch(poll_interval, idle_wait)

    def _batch_body(self, messages: list[dict], response_model: Type[BaseModel]) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "response_format": type_to_response_format_param(response_model),
            "prompt_cache_key": self._cache_key(messages),
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        return body

    async def _submit(self, todo) -> str:
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
        return batch.id

    async def _collect(self, batch_id: str) -> dict[str, str | Exception]:
        """Waits for the batch to finish, checkpoints each success, and returns
        raw JSON or an error per custom_id."""
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
        self._checkpoint_raw(key, message["content"])
        return key, message["content"]
