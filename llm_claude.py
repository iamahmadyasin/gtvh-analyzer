"""
Claude client: the same `call_structured(...) -> PydanticModel` contract as
the OpenAI client (llm.py), on the Anthropic Messages API.

- Structured outputs: `client.beta.messages.parse(output_format=Model)`
  constrains the response to the stage's Pydantic schema and returns it
  validated as `parsed_output`.
- Prompt caching: the system prompt and the parts of the user message that
  every call in a stage shares (the full story, the target inventory) carry
  `cache_control` breakpoints, so after the first call they are billed at
  the cache-read rate. The call-specific part comes last, uncached.
- Thinking and effort: current Claude models think adaptively by default
  (on Claude Opus 5.5 thinking cannot be turned off). Depth is set with
  `output_config.effort`; the default here is "high" because annotation is
  judgement-heavy, and Claude Opus 5.5's own default is "medium".
- No temperature: current Claude models reject sampling parameters.
- Refusals: a declined request (`stop_reason == "refusal"`) raises instead
  of returning a half-filled object. On models that support it, requests
  opt into server-side fallback (`fallbacks: "default"`), which re-runs a
  declined request on the model Anthropic recommends for that category.
- Retries: the SDK retries rate limits (429), overload and server errors
  with backoff; `max_retries` is raised for low tokens-per-minute accounts.
- No embeddings API: `embed` raises, and normalization falls back to string
  similarity.

Credentials come from the environment (ANTHROPIC_API_KEY, or an
`ant auth login` profile).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Type

import anthropic

from llm_base import BaseLLMClient, T

# Models that accept server-side refusal fallback in its "default" form.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that reject the effort parameter.
NO_EFFORT_PREFIXES = ("claude-haiku-4-5", "claude-sonnet-4-5")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def is_claude_model(model: str) -> bool:
    return model.startswith("claude-")


class ClaudeClient(BaseLLMClient):
    def __init__(
        self,
        model: str,
        effort: str | None = "high",
        max_tokens: int = 16000,
        fallback: bool = True,
        max_retries: int = 6,
        api_key: str | None = None,
        verbose: bool = True,
        checkpoint_dir: Path | None = None,
        fresh: bool = False,
    ):
        # Temperature is never sent to Claude.
        super().__init__(model, None, verbose, checkpoint_dir, fresh)
        if effort is not None and effort not in EFFORT_LEVELS:
            raise ValueError(f"effort must be one of {', '.join(EFFORT_LEVELS)}")
        self.effort = None if model.startswith(NO_EFFORT_PREFIXES) else effort
        self.max_tokens = max_tokens
        self.fallback = fallback and model in FALLBACK_MODELS
        kwargs = {"max_retries": max_retries}
        if api_key:
            kwargs["api_key"] = api_key
        self.client = anthropic.AsyncAnthropic(**kwargs)

    def _checkpoint_settings(self) -> dict:
        # Effort changes the answer; the provider keeps Claude and OpenAI
        # results apart even for identical messages.
        return {"provider": "anthropic", "model": self.model, "effort": self.effort}

    @staticmethod
    def _claude_request(messages: list[dict]) -> tuple[list[dict], list[dict]]:
        """System blocks and one user turn, with cache breakpoints after the
        system prompt and after the last shared part of the user message."""
        system = [{"type": "text", "text": messages[0]["content"],
                   "cache_control": {"type": "ephemeral"}}]
        blocks = [{"type": "text", "text": m["content"]} for m in messages[1:]]
        if len(blocks) > 1:
            blocks[-2]["cache_control"] = {"type": "ephemeral"}
        return system, [{"role": "user", "content": blocks}]

    def _request_params(self, messages: list[dict]) -> dict:
        system, claude_messages = self._claude_request(messages)
        params: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": claude_messages,
        }
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        return params

    def _record_usage(self, usage) -> None:
        if usage is None:
            return
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.usage.api_calls += 1
        self.usage.input_tokens += (getattr(usage, "input_tokens", 0) or 0) + cache_read + cache_write
        self.usage.cached_input_tokens += cache_read
        self.usage.output_tokens += getattr(usage, "output_tokens", 0) or 0

    @staticmethod
    def _check_stop(response, what: str) -> None:
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise RuntimeError(
                f"Claude declined the {what} request"
                + (f" (category: {category})" if category else "")
            )
        if response.stop_reason == "max_tokens":
            raise RuntimeError(f"Claude hit max_tokens on {what}; raise --claude-max-tokens")

    async def call_structured(
        self,
        system_prompt: str,
        user_message: str | Sequence[str],
        response_model: Type[T],
    ) -> T:
        """`user_message` may be a list: put the parts shared across calls
        (e.g. the full story) first and the call-specific part last, so the
        shared prefix is served from the prompt cache."""
        messages = self._messages(system_prompt, user_message)
        checkpoint = self._checkpoint_path(messages, response_model)
        cached = self._load_checkpoint(checkpoint, response_model)
        if cached is not None:
            self.usage.checkpoint_hits += 1
            return cached

        params = self._request_params(messages)
        if self.fallback:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        response = await self.client.beta.messages.parse(output_format=response_model, **params)
        self._record_usage(response.usage)
        self._check_stop(response, response_model.__name__)
        if self.verbose and any(b.type == "fallback" for b in response.content):
            print(f"    {self.model} declined; served by {response.model}")
        result = response.parsed_output
        if result is None:
            raise RuntimeError(f"Claude returned no parsed {response_model.__name__}")
        self._save_checkpoint(checkpoint, result)
        return result
