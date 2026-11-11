"""Defences around untrusted text and model output.

None of this is the primary control: prices are computed by code from validated hours and rates,
and the model has no tools. These checks quarantine obvious injection attempts, keep delimiters
intact and flag model prose that states figures or makes uncited claims, so a human sees them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from dealdesk.application.schemas import ExperienceClaim, ExtractedRequirement

_DELIMITER_TAG = re.compile(r"</?\s*untrusted_[a-z_]*\s*>", re.IGNORECASE)
_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\b.{0,40}\b(instructions|rules|prompts?)\b",
        r"\bdisregard\b.{0,40}\b(instructions|rules|prompts?)\b",
        r"\b(forget|override)\b.{0,30}\b(instructions|rules|system prompt)\b",
        r"^\s*(-\s*)?(system|assistant)\s*:",
        r"\b(reveal|print|show)\b.{0,30}\b(system prompt|your prompt|instructions)\b",
        r"\bset\b.{0,30}\b(price|rate|margin|discount)\b.{0,20}\bto\b",
        r"\b(approve|accept)\b.{0,30}\b(automatically|this quote|without review)\b",
        r"\byou are now\b",
        r"\badmin mode\b",
    )
)
_MONEY_OR_PERCENT = re.compile(r"(£|\$|€|\bGBP\b|\bUSD\b)\s?\d|\d+(\.\d+)?\s?%")
MAX_BRIEF_CHARS = 60_000


def neutralise_delimiters(text: str) -> str:
    """Remove anything that looks like our delimiter tags so data cannot close its own block."""
    return _DELIMITER_TAG.sub("[removed tag]", text)


def prepare_brief(text: str) -> str:
    """Normalise untrusted brief text before it is placed inside a prompt."""
    cleaned = neutralise_delimiters(text.replace("\x00", "")).strip()
    return cleaned[:MAX_BRIEF_CHARS]


def looks_like_injection(text: str) -> bool:
    """Return True if a line of text matches a known prompt-injection pattern."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def injection_lines(brief: str) -> list[str]:
    """Return the lines of a brief that look like injection attempts."""
    return [
        line.strip() for line in brief.splitlines() if line.strip() and looks_like_injection(line)
    ]


@dataclass(frozen=True, slots=True)
class ScreenedRequirements:
    """Requirements split into those kept and those quarantined as suspected injection."""

    kept: tuple[ExtractedRequirement, ...]
    quarantined: tuple[ExtractedRequirement, ...]


def screen_requirements(requirements: Iterable[ExtractedRequirement]) -> ScreenedRequirements:
    """Quarantine requirements that look like instructions to the model rather than scope."""
    kept: list[ExtractedRequirement] = []
    quarantined: list[ExtractedRequirement] = []
    for requirement in requirements:
        (quarantined if looks_like_injection(requirement.text) else kept).append(requirement)
    return ScreenedRequirements(tuple(kept), tuple(quarantined))


def states_figures(texts: Iterable[str]) -> bool:
    """Return True if model prose contains currency amounts or percentages."""
    return any(_MONEY_OR_PERCENT.search(text) for text in texts)


def uncited_claims(claims: Sequence[ExperienceClaim], allowed_ids: set[str]) -> list[int]:
    """Return indexes of claims with no source, or citing ids that were not retrieved."""
    return [
        index
        for index, claim in enumerate(claims)
        if not claim.source_ids or not set(claim.source_ids) <= allowed_ids
    ]


def data_block(payload: object) -> str:
    """Serialise code-built context (which may contain untrusted strings) for a prompt."""
    return neutralise_delimiters(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
