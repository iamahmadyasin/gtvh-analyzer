"""Tests for the Claude provider, against a stand-in for the Anthropic API.

Run with:  python -m unittest discover tests
No API key or network needed.
"""

import argparse
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from batch_claude import ClaudeBatchClient
from llm_claude import FALLBACK_BETA, ClaudeClient
from providers import resolve_provider
from schemas import SegmentationResult


def _seg_result():
    return SegmentationResult(segments=[])


def _usage(inp=10, read=0, write=0, out=5):
    return NS(input_tokens=inp, cache_read_input_tokens=read,
              cache_creation_input_tokens=write, output_tokens=out)


class FakeMessages:
    def __init__(self, stop_reason="end_turn", parsed=None):
        self.calls = []
        self.stop_reason = stop_reason
        self.parsed = parsed

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        parsed = None if self.stop_reason == "refusal" else (self.parsed or kwargs["output_format"](segments=[]))
        return NS(parsed_output=parsed, stop_reason=self.stop_reason,
                  stop_details=NS(category="cyber") if self.stop_reason == "refusal" else None,
                  usage=_usage(read=100), content=[], model=kwargs["model"])


def _client(model="claude-opus-5-5", tmp=None, fake=None, **kw):
    c = ClaudeClient(model, api_key="test", checkpoint_dir=tmp, verbose=False, **kw)
    c.client = NS(beta=NS(messages=fake or FakeMessages()))
    return c


class RequestShapeTests(unittest.TestCase):
    def test_cache_breakpoints_effort_fallback_no_temperature(self):
        fake = FakeMessages()
        c = _client(fake=fake)
        asyncio.run(c.call_structured("SYSTEM", ["STORY", "INVENTORY", "TASK"], SegmentationResult))
        kw = fake.calls[0]
        self.assertEqual(kw["system"], [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}])
        blocks = kw["messages"][0]["content"]
        self.assertEqual([b["text"] for b in blocks], ["STORY", "INVENTORY", "TASK"])
        # breakpoint on the last shared part, none on the call-specific task
        self.assertEqual([("cache_control" in b) for b in blocks], [False, True, False])
        self.assertEqual(kw["output_config"], {"effort": "high"})
        self.assertEqual(kw["betas"], [FALLBACK_BETA])
        self.assertEqual(kw["fallbacks"], "default")
        self.assertIs(kw["output_format"], SegmentationResult)
        for forbidden in ("temperature", "top_p", "top_k", "thinking"):
            self.assertNotIn(forbidden, kw)

    def test_single_part_and_model_specific_options(self):
        fake = FakeMessages()
        c = _client("claude-haiku-4-5", fake=fake)
        asyncio.run(c.call_structured("S", "ONLY", SegmentationResult))
        kw = fake.calls[0]
        self.assertNotIn("cache_control", kw["messages"][0]["content"][0])
        self.assertNotIn("output_config", kw)        # Haiku 4.5 rejects effort
        self.assertNotIn("fallbacks", kw)            # no server-side fallback there
        fake2 = FakeMessages()
        asyncio.run(_client(fake=fake2, fallback=False, effort="low").call_structured("S", "X", SegmentationResult))
        self.assertNotIn("fallbacks", fake2.calls[0])
        self.assertEqual(fake2.calls[0]["output_config"], {"effort": "low"})


class OutcomeTests(unittest.TestCase):
    def test_refusal_and_max_tokens_raise(self):
        with self.assertRaisesRegex(RuntimeError, "declined.*cyber"):
            asyncio.run(_client(fake=FakeMessages("refusal")).call_structured("S", "X", SegmentationResult))
        with self.assertRaisesRegex(RuntimeError, "max_tokens"):
            asyncio.run(_client(fake=FakeMessages("max_tokens")).call_structured("S", "X", SegmentationResult))

    def test_usage_and_checkpoint_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeMessages()
            c = _client(tmp=Path(tmp), fake=fake)
            asyncio.run(c.call_structured("S", ["A", "B"], SegmentationResult))
            self.assertEqual((c.usage.api_calls, c.usage.input_tokens, c.usage.cached_input_tokens,
                              c.usage.output_tokens), (1, 110, 100, 5))
            c2 = _client(tmp=Path(tmp), fake=fake)
            asyncio.run(c2.call_structured("S", ["A", "B"], SegmentationResult))
            self.assertEqual((len(fake.calls), c2.usage.checkpoint_hits), (1, 1))
            # A different effort is a different answer: not served from the checkpoint
            asyncio.run(_client(tmp=Path(tmp), fake=fake, effort="low").call_structured("S", ["A", "B"], SegmentationResult))
            self.assertEqual(len(fake.calls), 2)


class ProviderTests(unittest.TestCase):
    def test_auto_detection(self):
        ns = lambda m, p="auto": argparse.Namespace(model=m, provider=p)
        self.assertEqual(resolve_provider(ns("claude-opus-5-5")), "claude")
        self.assertEqual(resolve_provider(ns("gpt-5.6-luna")), "openai")
        self.assertEqual(resolve_provider(ns("my-proxy-model", "claude")), "claude")

    def test_no_embeddings_falls_back_to_string(self):
        from normalize import make_similarity, string_similarity
        c = _client()

        async def embed(texts):
            return await c.embed(texts, "x")

        sim, used = asyncio.run(make_similarity(["a party", "the party"], "embeddings", embed))
        self.assertEqual(used, "string")
        self.assertIs(sim, string_similarity)


class FakeBatches:
    def __init__(self):
        self.created = []

    async def create(self, requests):
        self.created.append(requests)
        return NS(id=f"msgbatch_{len(self.created)}")

    async def retrieve(self, batch_id):
        n = len(self.created[int(batch_id.split("_")[1]) - 1])
        return NS(processing_status="ended",
                  request_counts=NS(processing=0, succeeded=n, errored=0, canceled=0, expired=0))

    async def results(self, batch_id):
        reqs = self.created[int(batch_id.split("_")[1]) - 1]

        async def gen():
            for r in reqs:
                yield NS(custom_id=r["custom_id"], result=NS(type="succeeded", message=NS(
                    stop_reason="end_turn", usage=_usage(),
                    content=[NS(type="text", text=json.dumps({"segments": []}))])))
        return gen()


class BatchTests(unittest.TestCase):
    def test_batch_body_submit_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            batches = FakeBatches()
            c = ClaudeBatchClient("claude-opus-5-5", api_key="test", checkpoint_dir=Path(tmp),
                                  poll_interval=0, idle_wait=0.01, verbose=False)
            c.client = NS(messages=NS(batches=batches))

            async def run():
                return await asyncio.gather(
                    c.call_structured("S", ["STORY", "TASK 1"], SegmentationResult),
                    c.call_structured("S", ["STORY", "TASK 2"], SegmentationResult))

            out = asyncio.run(run())
            self.assertEqual([len(b) for b in batches.created], [2])      # one batch for both
            params = batches.created[0][0]["params"]
            self.assertEqual(params["output_config"]["effort"], "high")
            self.assertEqual(params["output_config"]["format"]["type"], "json_schema")
            self.assertNotIn("fallbacks", params)                          # not on the Batches API
            self.assertNotIn("temperature", params)
            self.assertEqual(out, [_seg_result(), _seg_result()])
            # results are checkpointed: an online client reuses them
            online = _client(tmp=Path(tmp), fake=FakeMessages())
            asyncio.run(online.call_structured("S", ["STORY", "TASK 1"], SegmentationResult))
            self.assertEqual(online.usage.checkpoint_hits, 1)
            self.assertFalse(list((Path(tmp) / "batches").glob("*.json")))  # record cleared


if __name__ == "__main__":
    unittest.main()
