"""Stage 1b: story-level target inventory.

One call per story, before annotation. Lists the characters, groups,
institutions, and ideas the story is likely to target, each tagged with a
few attributes, so the annotation stage can reuse one label per butt and
the text-level stage can build strands from targets that share a feature, 
not only from identical targets.
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
