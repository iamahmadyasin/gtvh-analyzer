from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

import schemas

PROMPTS_DIR = Path(__file__).parent / "prompts"


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    system: str
    templates: dict[str, str]

    def render(self, template: str, **values: object) -> str:
        try:
            return self.templates[template].format(**values)
        except KeyError as exc:
            raise PromptError(
                f"prompts/{self.name}.yaml: template {template!r} needs "
                f"field {exc}, or the template itself is missing"
            ) from exc


def _check_enums(name: str, system: str, enum_names: list[str]) -> None:
    problems: list[str] = []
    for enum_name in enum_names:
        enum_cls = getattr(schemas, enum_name, None)
        if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
            problems.append(f"{enum_name} is not an enum in schemas.py")
            continue
        missing = [m.value for m in enum_cls if f"`{m.value}`" not in system]
        if missing:
            problems.append(
                f"{enum_name} values not documented in `system`: "
                + ", ".join(f"`{v}`" for v in missing)
            )
    if problems:
        raise PromptError(f"prompts/{name}.yaml: " + "; ".join(problems))


def load_prompt(name: str) -> Prompt:
    """Load prompts/<name>.yaml. `name` is the stem (no extension)."""
    path = PROMPTS_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("system"), str):
        raise PromptError(f"{path.name}: needs a `system` text block")
    templates = data.get("templates") or {}
    if not all(isinstance(v, str) for v in templates.values()):
        raise PromptError(f"{path.name}: every template must be text")
    _check_enums(name, data["system"], data.get("enums") or [])
    return Prompt(
        name=name,
        version=data.get("version", 1),
        system=data["system"],
        templates=templates,
    )
