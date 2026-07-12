"""
Thin async wrapper around OpenAI's structured-output API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


class LLMClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        temperature: float | None = 0.0,
    ):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it, or put it in a .env file."
            )
        self.client = AsyncOpenAI(api_key=key)
        self.model = model
        self.temperature = temperature

    async def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_model: Type[T],
    ) -> T:
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "response_format": response_model,
        }
        # Some reasoning models reject `temperature`
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        completion = await self.client.chat.completions.parse(**kwargs)

        message = completion.choices[0].message
        if message.parsed is None:
            raise RuntimeError(
                f"Model returned no parsed content for {response_model.__name__}. "
                f"Refusal: {message.refusal!r}"
            )
        return message.parsed
