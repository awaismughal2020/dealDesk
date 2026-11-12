"""FakeLLM: a deterministic, offline stand-in for a language model (the default provider).

It answers from recorded fixtures when one exists for the exact prompt, otherwise from simple
rules over the same rendered prompt a real model would receive. It is deliberately naive: for
example it copies injected bullet points into the requirement list, so the guardrails that
screen model output are exercised for real. It never sees prices or rates.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dealdesk.adapters.llm.base import RawCompletion
from dealdesk.ports.llm import PromptSpec

PROVIDER = "fake"
CHARS_PER_TOKEN = 4
BASELINE_REQUIREMENTS = Decimal(8)
SCALE_MIN, SCALE_MAX = Decimal("0.5"), Decimal("1.5")
REVISION_SHIFT = Decimal("0.30")
MAX_CASE_STUDY_CLAIMS = 2
MIN_REQUIREMENT_WORDS = 4
SUMMARY_CHARS = 400
FIXTURE_KEY_CHARS = 16

_BLOCK = re.compile(r"<(untrusted_brief|untrusted_data)>\n(?P<body>.*)\n</\1>", re.DOTALL)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(?P<text>.+)$")
_TITLE_PREFIX = re.compile(r"^(sample\s+)?(rfp|itt|tender|request for proposal)\s*[:\-]\s*", re.I)
_AMBIGUOUS = re.compile(
    r"\b(maybe|not sure|tbc|to be confirmed|possibly|flexible|depends)\b|\?", re.I
)
_CATEGORIES = (
    ("integration", re.compile(r"integrat|\bapi\b|interface with", re.I)),
    ("security", re.compile(r"sign-on|\bsso\b|secur|identity|authentica", re.I)),
    ("non_functional", re.compile(r"wcag|accessib|responsive|performance|availability", re.I)),
    ("ux", re.compile(r"research|usability|user testing|design", re.I)),
    ("data", re.compile(r"\bdata\b|report|dashboard|analytics|extract", re.I)),
    ("delivery", re.compile(r"timeline|go live|deadline|measure", re.I)),
)


class FixtureMissingError(LookupError):
    """Strict replay mode was asked for a prompt with no recorded fixture."""


def fixture_key(prompt: PromptSpec) -> str:
    """Stable key for a prompt: id, version and a hash of the full rendered text."""
    digest = hashlib.sha256(
        "\x1f".join((prompt.prompt_id, prompt.version, prompt.system, prompt.user)).encode()
    ).hexdigest()
    return f"{prompt.prompt_id}.{digest[:FIXTURE_KEY_CHARS]}"


class FakeModelClient:
    """Implements `ModelClient` deterministically, with optional fixture replay."""

    def __init__(
        self,
        model: str = "fake-deterministic-v1",
        fixtures_dir: Path | None = None,
        *,
        strict: bool = False,
    ) -> None:
        self._model = model
        self._fixtures_dir = fixtures_dir
        self._strict = strict
        self._handlers: dict[str, Callable[[str], dict[str, Any]]] = {
            "extract_requirements": _extract,
            "estimate": _estimate,
            "revise_estimate": _revise,
            "draft_proposal": _draft,
        }

    @property
    def provider(self) -> str:
        """Provider name."""
        return PROVIDER

    @property
    def model(self) -> str:
        """Model name."""
        return self._model

    def complete(self, prompt: PromptSpec, schema: type[BaseModel]) -> RawCompletion:  # noqa: ARG002
        """Answer from a fixture if recorded, else from the rules for this prompt id."""
        text = self._replay(prompt)
        if text is None:
            if self._strict:
                raise FixtureMissingError(fixture_key(prompt))
            match = _BLOCK.search(prompt.user)
            body = match["body"] if match else ""
            text = json.dumps(self._handlers[prompt.prompt_id](body))
        return RawCompletion(text, _tokens(prompt.system + prompt.user), _tokens(text))

    def _replay(self, prompt: PromptSpec) -> str | None:
        if self._fixtures_dir is None:
            return None
        path = self._fixtures_dir / f"{fixture_key(prompt)}.json"
        if not path.exists():
            return None
        recorded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(recorded["output"])


def _tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


# ---------------------------------------------------------------- extraction


def _extract(brief: str) -> dict[str, Any]:
    lines = [line.rstrip() for line in brief.splitlines()]
    non_empty = [line.strip() for line in lines if line.strip()]
    title = _TITLE_PREFIX.sub("", non_empty[0]) if non_empty else "Untitled brief"
    requirements: list[dict[str, str]] = []
    ambiguities: list[str] = []
    for line in lines:
        bullet = _BULLET.match(line)
        text = bullet["text"].strip() if bullet else ""
        if (
            not text
            and re.search(r"\b(shall|must)\b", line, re.I)
            and not line.strip().endswith(":")
        ):
            text = line.strip()
        if len(text.split()) < MIN_REQUIREMENT_WORDS:
            continue
        requirements.append(
            {
                "ref": f"R-{len(requirements) + 1}",
                "text": text[:500],
                "category": _category(text),
                "priority": _priority(text),
            }
        )
        if _AMBIGUOUS.search(text):
            ambiguities.append(f"Please clarify: {text[:200]}")
    paragraphs = [p.strip() for p in brief.split("\n\n") if p.strip()]
    summary = " ".join(paragraphs[1:2])[:SUMMARY_CHARS] if len(paragraphs) > 1 else ""
    return {
        "title": title[:200],
        "summary": summary,
        "requirements": requirements,
        "ambiguities": ambiguities,
    }


def _category(text: str) -> str:
    return next((name for name, pattern in _CATEGORIES if pattern.search(text)), "functional")


def _priority(text: str) -> str:
    if re.search(r"\b(maybe|possibly|could|nice to have|tbc)\b|\?", text, re.I):
        return "could"
    if re.search(r"\b(shall|must|required)\b", text, re.I):
        return "must"
    return "should"


# ---------------------------------------------------------------- estimation


def _whole_hours(value: Decimal) -> str:
    return str(max(Decimal(1), value.quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def _estimate(body: str) -> dict[str, Any]:
    context = json.loads(body)
    allowed = set(context["allowed_roles"])
    references = context["reference_projects"]
    best: dict[str, Any] = (
        references[0] if references else {"id": "none", "actual_hours_by_role": {}}
    )
    count = Decimal(len(context["requirements"]))
    scale = min(SCALE_MAX, max(SCALE_MIN, count / BASELINE_REQUIREMENTS)).quantize(Decimal("0.05"))
    roles = [
        {"role": role, "hours": _whole_hours(Decimal(hours) * scale)}
        for role, hours in sorted(best["actual_hours_by_role"].items())
        if role in allowed
    ]
    return {
        "roles": roles or [{"role": sorted(allowed)[0], "hours": "40"}],
        "rationale": (
            f"Based on the actual hours of the most similar reference project ({best['id']}), "
            f"scaled to {len(context['requirements'])} requirements against a baseline of "
            f"{BASELINE_REQUIREMENTS}."
        ),
        "reference_project_ids": [best["id"]] if references else [],
        "assumptions": [
            "Scope is limited to the requirements listed.",
            "Client provides timely access to systems.",
        ],
    }


def _revise(body: str) -> dict[str, Any]:
    context = json.loads(body)
    allowed = set(context["allowed_roles"])
    hours = {item["role"]: Decimal(item["hours"]) for item in context["previous_estimate"]}
    notes = []
    for issue in context.get("issues", []):
        role = issue["role"]
        if issue["code"] == "ABOVE_CEILING":
            hours[role] = Decimal(context["max_hours_per_role"])
            notes.append(
                f"Capped {role} at the stated ceiling and moved the remainder into assumptions."
            )
        else:
            hours.pop(role, None)
            notes.append(f"Removed invalid entry for {role}.")
    ranking = [r for r in context.get("roles_by_margin_lowest_first", []) if r in hours]
    if len(ranking) > 1:
        source = ranking[0]
        better_half = ranking[len(ranking) // 2 :]
        target = max(better_half, key=lambda role: (hours[role], role))
        moved = (hours[source] * REVISION_SHIFT).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        hours[source] -= moved
        hours[target] += moved
        notes.append(f"Moved {moved} hours from {source} to {target}, where the work allows it.")
    roles = [
        {"role": role, "hours": _whole_hours(value)}
        for role, value in sorted(hours.items())
        if role in allowed and value > 0
    ]
    return {
        "roles": roles or [{"role": sorted(allowed)[0], "hours": "40"}],
        "rationale": " ".join(notes) or "No change was needed.",
        "reference_project_ids": context.get("reference_project_ids", []),
        "assumptions": ["Hour allocation revised; rates are unchanged and set by code."],
    }


# ---------------------------------------------------------------- proposal


def _draft(body: str) -> dict[str, Any]:
    context = json.loads(body)
    requirements = context["requirements"]
    roles = ", ".join(item["role"].replace("_", " ") for item in context["team"])
    comment = context.get("reviewer_comment")
    summary = (
        f"We propose to deliver {context['title']} as a focused, phased engagement covering all "
        f"{len(requirements)} stated requirements, with a human-reviewed plan at each stage."
    )
    if comment:
        summary += f" This draft has been revised to address reviewer feedback: {comment}"
    return {
        "executive_summary": summary,
        "understanding": "You have asked for: "
        + "; ".join(r["text"] for r in requirements[:6])
        + ".",
        "scope_and_deliverables": [f"{r['ref']}: {r['text']}" for r in requirements],
        "approach": (
            "Discovery and design first, then iterative delivery in short increments with "
            "demonstrations, automated testing and an accessibility review before go-live."
        ),
        "team_and_timeline": f"A blended team ({roles}) working in fortnightly increments.",
        "assumptions_and_exclusions": [
            *context.get("ambiguities", []),
            "Hosting costs are excluded.",
        ],
        "relevant_experience": [
            {"text": f"{cs['title']}: {cs['summary']}", "source_ids": [cs["id"]]}
            for cs in context["case_studies"][:MAX_CASE_STUDY_CLAIMS]
        ],
    }
