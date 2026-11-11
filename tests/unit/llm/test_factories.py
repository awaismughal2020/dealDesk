from typing import Any

import pytest
from pydantic import SecretStr

from dealdesk.adapters.embeddings import factory as embedding_factory
from dealdesk.adapters.embeddings.fake import FakeEmbedder
from dealdesk.adapters.llm import factory
from dealdesk.adapters.llm.fake import FakeModelClient
from dealdesk.config import Settings


class Stub:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def settings(**kwargs: Any) -> Settings:
    return Settings(cookie_secure=False, **kwargs)


def test_default_is_fake_and_offline() -> None:
    llm = factory.build_llm(settings())
    assert isinstance(factory.build_model_client(settings()), FakeModelClient)
    assert llm is not None


@pytest.mark.parametrize(
    ("provider", "module", "cls", "extra"),
    [
        (
            "vertex",
            "dealdesk.adapters.llm.vertex",
            "VertexModelClient",
            {"google_cloud_project": "demo"},
        ),
        (
            "anthropic",
            "dealdesk.adapters.llm.anthropic_client",
            "AnthropicModelClient",
            {"anthropic_api_key": SecretStr("k")},
        ),
        (
            "openai",
            "dealdesk.adapters.llm.openai_client",
            "OpenAIModelClient",
            {"openai_api_key": SecretStr("k")},
        ),
    ],
)
def test_real_providers_are_opt_in(
    monkeypatch: pytest.MonkeyPatch, provider: str, module: str, cls: str, extra: dict[str, Any]
) -> None:
    monkeypatch.setattr(f"{module}.{cls}", Stub)
    client = factory.build_model_client(
        settings(llm_provider=provider, llm_model="configured-model", **extra)
    )
    assert isinstance(client, Stub)
    assert client.kwargs["model"] == "configured-model"


@pytest.mark.parametrize(
    ("provider", "cls", "extra"),
    [
        ("vertex", "VertexEmbedder", {"google_cloud_project": "demo"}),
        ("openai", "OpenAIEmbedder", {"openai_api_key": SecretStr("k")}),
    ],
)
def test_embedder_factory(
    monkeypatch: pytest.MonkeyPatch, provider: str, cls: str, extra: dict[str, Any]
) -> None:
    monkeypatch.setattr(embedding_factory, cls, Stub)
    embedder = embedding_factory.build_embedder(settings(embedding_provider=provider, **extra))
    assert isinstance(embedder, Stub)
    assert embedder.kwargs["dim"] == 256
    assert isinstance(embedding_factory.build_embedder(settings()), FakeEmbedder)


def test_fake_embedder_is_deterministic_and_normalised() -> None:
    embedder = FakeEmbedder(dim=16)
    first, second, empty = embedder.embed(
        ["tenant portal repairs", "tenant portal repairs", "the and"]
    )
    assert first == second
    assert abs(sum(v * v for v in first) - 1) < 1e-9
    assert empty[0] == 1.0
    assert (embedder.model, embedder.dim) == ("fake-hashing-v1", 16)
