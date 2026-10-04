"""
Utility · Text helpers
Numbers the story's lines for the prompts.

Reads:   the story text
Writes:  the numbered text, one 'Line N: ...' per line
"""

from __future__ import annotations


def number_lines(text: str) -> str:
    return "\n".join(
        f"Line {i + 1}: {line}" for i, line in enumerate(text.splitlines())
    )
