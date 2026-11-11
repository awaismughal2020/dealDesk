from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from dealdesk.adapters.embeddings.fake import FakeEmbedder
from dealdesk.adapters.llm.base import StructuredLLM
from dealdesk.adapters.llm.fake import FakeModelClient
from dealdesk.adapters.reference_memory import InMemoryReferenceData
from dealdesk.application.pipeline import DealPipeline
from dealdesk.config import Settings
from dealdesk.ports.llm import LLMPort, LLMResult, LLMUsage, PromptSpec

ROOT = Path(__file__).resolve().parents[3]


class ScriptedLLM:
    """LLMPort double: answers by prompt id from queued JSON strings, else delegates to the fake."""

    def __init__(self, scripts: dict[str, list[str]]) -> None:
        self.scripts = scripts
        self.prompts: list[PromptSpec] = []
        self.fallback = StructuredLLM(FakeModelClient(), max_retries=0)

    def generate[T: BaseModel](self, prompt: PromptSpec, schema: type[T]) -> LLMResult[T]:
        self.prompts.append(prompt)
        queue = self.scripts.get(prompt.prompt_id)
        if queue:
            usage = LLMUsage("scripted", "m", 1, 1, 0, 1)
            return LLMResult(schema.model_validate_json(queue.pop(0)), usage)
        return self.fallback.generate(prompt, schema)


@pytest.fixture(scope="session")
def reference() -> InMemoryReferenceData:
    return InMemoryReferenceData(ROOT / "data" / "seed", FakeEmbedder())


@pytest.fixture
def make_pipeline(reference: InMemoryReferenceData) -> Callable[..., DealPipeline]:
    def build(llm: LLMPort | None = None, **overrides: object) -> DealPipeline:
        settings = Settings(cookie_secure=False)
        options: dict[str, object] = {
            "llm": llm or StructuredLLM(FakeModelClient(), max_retries=0),
            "embedder": FakeEmbedder(),
            "reference": reference,
            "policy": settings.costing_policy,
            "top_k": 3,
            "max_revisions": 2,
        }
        options.update(overrides)
        return DealPipeline(**options)  # type: ignore[arg-type]

    return build


@pytest.fixture
def brief() -> Callable[[str], str]:
    return lambda name: (ROOT / "data" / "samples" / f"{name}.txt").read_text(encoding="utf-8")
