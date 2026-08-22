from __future__ import annotations


def number_lines(text: str) -> str:
    return "\n".join(
        f"Line {i + 1}: {line}" for i, line in enumerate(text.splitlines())
    )
