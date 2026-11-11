"""Versioned prompt templates stored as files. The version is recorded with every model call."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from string import Template

from dealdesk.ports.llm import PromptSpec

_HEADER = re.compile(
    r"^---\nid: (?P<id>[a-z_]+)\nversion: (?P<version>[0-9.]+)\n---\n", re.MULTILINE
)
_SECTIONS = re.compile(
    r"^\[system\]\n(?P<system>.*?)^\[user\]\n(?P<user>.*)\Z", re.DOTALL | re.MULTILINE
)


class PromptFormatError(ValueError):
    """A prompt file is malformed."""


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A prompt loaded from `application/prompts/<name>.md`."""

    prompt_id: str
    version: str
    system: str
    user: str

    def render(self, **values: str) -> PromptSpec:
        """Fill `$placeholders` in the user section. Missing values raise `KeyError`."""
        return PromptSpec(
            prompt_id=self.prompt_id,
            version=self.version,
            system=self.system,
            user=Template(self.user).substitute(values),
        )


def _read(name: str) -> str:
    return resources.files(__name__).joinpath(f"{name}.md").read_text(encoding="utf-8")


@cache
def load_prompt(name: str) -> PromptTemplate:
    """Load and parse a prompt file; shared security rules are inlined into the system part."""
    text = _read(name)
    header = _HEADER.match(text)
    sections = _SECTIONS.search(text[header.end() :]) if header else None
    if header is None or sections is None:
        raise PromptFormatError(f"prompt {name!r} must have a header and [system]/[user] sections")
    system = Template(sections["system"].strip()).substitute(
        shared_rules=_read("_shared_rules").strip()
    )
    return PromptTemplate(header["id"], header["version"], system, sections["user"].strip())
