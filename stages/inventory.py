"""
Stage 1b · Target inventory
Lists the characters, groups, institutions and ideas the story may target, so
annotation reuses one label per butt.

Reads:   the numbered story
Writes:  a list of TargetEntry, with ids T-01, T-02, ...
"""

from __future__ import annotations

from llm_base import BaseLLMClient
from promptlib import load_prompt
from schemas import TargetEntry, TargetInventory


async def build_inventory(story_text_numbered: str, llm: BaseLLMClient) -> list[TargetEntry]:
    prompt = load_prompt("target_inventory")
    result = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=prompt.render("task", story=story_text_numbered),
        response_model=TargetInventory,
    )
    for i, entry in enumerate(result.targets, start=1):
        entry.target_id = f"T-{i:02d}"
    return result.targets


def format_inventory(inventory: list[TargetEntry]) -> str:
    if not inventory:
        return "(empty: no likely targets were identified)"
    rows = []
    for e in inventory:
        aka = f" | also: {', '.join(e.aliases)}" if e.aliases else ""
        rows.append(
            f"- {e.target_id} | {e.label} | {e.kind.value}, "
            f"class {e.social_class.value}, sphere {e.sphere.value}"
            f"{aka} | {e.description}"
        )
    return "\n".join(rows)
