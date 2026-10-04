"""
Model clients · Provider choice
Picks OpenAI or Claude from --model and --provider, and builds the client.

Reads:   command-line arguments
Writes:  a model client
"""

from __future__ import annotations

import argparse
from pathlib import Path

from llm_claude import EFFORT_LEVELS, is_claude_model


def add_provider_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("model provider")
    group.add_argument(
        "--provider", choices=["auto", "openai", "claude"], default="auto",
        help="Which API serves --model. 'auto' (default): Claude for model names "
             "starting with 'claude-', OpenAI otherwise.")
    group.add_argument(
        "--effort", choices=EFFORT_LEVELS, default="high",
        help="Claude only: how much the model thinks before answering (default: high; "
             "Claude Opus 5.5's own default is medium). Lower is cheaper.")
    group.add_argument(
        "--claude-max-tokens", type=int, default=16000,
        help="Claude only: output cap per call, thinking included (default: 16000).")
    group.add_argument(
        "--no-fallback", action="store_true",
        help="Claude only: don't re-run a declined request on Anthropic's "
             "recommended fallback model.")


def resolve_provider(args: argparse.Namespace) -> str:
    if args.provider != "auto":
        return args.provider
    return "claude" if is_claude_model(args.model) else "openai"


def make_client(args: argparse.Namespace, checkpoint_dir: Path, *, batch: bool = False,
                temperature: float | None = None):
    if resolve_provider(args) == "claude":
        if batch:
            from batch_claude import ClaudeBatchClient as cls
        else:
            from llm_claude import ClaudeClient as cls
        return cls(model=args.model, effort=args.effort, max_tokens=args.claude_max_tokens,
                   fallback=not args.no_fallback, checkpoint_dir=checkpoint_dir, fresh=args.fresh)
    if batch:
        from batch_openai import BatchLLMClient as cls
    else:
        from llm_openai import LLMClient as cls
    return cls(model=args.model, temperature=temperature,
               checkpoint_dir=checkpoint_dir, fresh=args.fresh)
