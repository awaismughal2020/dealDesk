"""Provider adapters, exercised with stub SDK clients (no network, no credentials)."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import openai
import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel

from dealdesk.adapters.embeddings.providers import OpenAIEmbedder, VertexEmbedder
from dealdesk.adapters.llm.anthropic_client import AnthropicModelClient
from dealdesk.adapters.llm.base import TransientLLMError
from dealdesk.adapters.llm.openai_client import OpenAIModelClient
from dealdesk.adapters.llm.vertex import VertexModelClient
from dealdesk.ports.llm import PromptSpec

PROMPT = PromptSpec("p", "1", "sys", "user")
REQUEST = httpx.Request("POST", "https://example.invalid")


class Out(BaseModel):
    value: int


class Recorder:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result, self.error, self.kwargs = result, error, {}

    def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


# ---------------------------------------------------------------- vertex


def vertex(call: Recorder) -> VertexModelClient:
    stub = SimpleNamespace(models=SimpleNamespace(generate_content=call))
    return VertexModelClient(
        project="p",
        location="l",
        model="gemini-x",
        temperature=0.1,
        timeout_seconds=5,
        max_output_tokens=100,
        client=stub,
    )


def test_vertex_success_sends_schema_and_counts_tokens() -> None:
    usage = SimpleNamespace(prompt_token_count=7, candidates_token_count=3)
    call = Recorder(SimpleNamespace(text='{"value": 1}', usage_metadata=usage))
    client = vertex(call)
    raw = client.complete(PROMPT, Out)
    assert (raw.text, raw.input_tokens, raw.output_tokens) == ('{"value": 1}', 7, 3)
    assert (client.provider, client.model, call.kwargs["model"]) == (
        "vertex",
        "gemini-x",
        "gemini-x",
    )
    config = call.kwargs["config"]
    assert config.response_json_schema["properties"]["value"]["type"] == "integer"
    assert config.system_instruction == "sys"


def test_vertex_without_usage_or_text() -> None:
    raw = vertex(Recorder(SimpleNamespace(text=None, usage_metadata=None))).complete(PROMPT, Out)
    assert (raw.text, raw.input_tokens) == ("", 0)


def test_vertex_error_mapping() -> None:
    with pytest.raises(TransientLLMError):
        vertex(Recorder(error=genai_errors.ServerError(503, {}))).complete(PROMPT, Out)
    with pytest.raises(TransientLLMError, match="rate limited"):
        vertex(Recorder(error=genai_errors.ClientError(429, {}))).complete(PROMPT, Out)
    with pytest.raises(genai_errors.ClientError):
        vertex(Recorder(error=genai_errors.ClientError(400, {}))).complete(PROMPT, Out)


# ---------------------------------------------------------------- anthropic


def claude(call: Recorder) -> AnthropicModelClient:
    stub = SimpleNamespace(messages=SimpleNamespace(parse=call))
    return AnthropicModelClient(
        api_key="k", model="claude-x", timeout_seconds=5, max_output_tokens=50, client=stub
    )


def test_anthropic_parsed_output() -> None:
    message = SimpleNamespace(
        parsed_output=Out(value=4),
        usage=SimpleNamespace(input_tokens=9, output_tokens=2),
        content=[],
    )
    call = Recorder(message)
    raw = claude(call).complete(PROMPT, Out)
    assert (raw.text, raw.input_tokens, raw.output_tokens) == ('{"value":4}', 9, 2)
    assert call.kwargs["output_format"] is Out
    assert "temperature" not in call.kwargs
    assert claude(call).provider == "anthropic"
    assert claude(call).model == "claude-x"


def test_anthropic_falls_back_to_text_blocks() -> None:
    message = SimpleNamespace(
        parsed_output=None,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        content=[
            SimpleNamespace(text='{"value"'),
            SimpleNamespace(type="other"),
            SimpleNamespace(text=": 5}"),
        ],
    )
    assert claude(Recorder(message)).complete(PROMPT, Out).text == '{"value": 5}'


def test_anthropic_transient_errors() -> None:
    with pytest.raises(TransientLLMError, match="APITimeoutError"):
        claude(Recorder(error=anthropic.APITimeoutError(REQUEST))).complete(PROMPT, Out)


# ---------------------------------------------------------------- openai


def gpt(call: Recorder) -> OpenAIModelClient:
    stub = SimpleNamespace(responses=SimpleNamespace(parse=call))
    return OpenAIModelClient(
        api_key="k",
        model="gpt-x",
        temperature=0.1,
        timeout_seconds=5,
        max_output_tokens=50,
        client=stub,
    )


def test_openai_parsed_output_and_fallback() -> None:
    usage = SimpleNamespace(input_tokens=4, output_tokens=6)
    call = Recorder(SimpleNamespace(output_parsed=Out(value=8), usage=usage, output_text=""))
    raw = gpt(call).complete(PROMPT, Out)
    assert (raw.text, raw.input_tokens, raw.output_tokens) == ('{"value":8}', 4, 6)
    assert call.kwargs["text_format"] is Out
    fallback = gpt(
        Recorder(SimpleNamespace(output_parsed=None, usage=None, output_text="raw"))
    ).complete(PROMPT, Out)
    assert (fallback.text, fallback.input_tokens) == ("raw", 0)
    assert (gpt(call).provider, gpt(call).model) == ("openai", "gpt-x")


def test_openai_transient_errors() -> None:
    with pytest.raises(TransientLLMError):
        gpt(Recorder(error=openai.APIConnectionError(request=REQUEST))).complete(PROMPT, Out)


# ---------------------------------------------------------------- embeddings


def test_vertex_embedder() -> None:
    call = Recorder(SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])]))
    embedder = VertexEmbedder(
        project="p",
        location="l",
        model="emb",
        dim=2,
        client=SimpleNamespace(models=SimpleNamespace(embed_content=call)),
    )
    assert embedder.embed(["x"]) == [[0.1, 0.2]]
    assert call.kwargs["config"].output_dimensionality == 2
    assert (embedder.model, embedder.dim) == ("emb", 2)


def test_openai_embedder() -> None:
    call = Recorder(SimpleNamespace(data=[SimpleNamespace(embedding=[0.3])]))
    embedder = OpenAIEmbedder(
        api_key="k",
        model="emb",
        dim=1,
        client=SimpleNamespace(embeddings=SimpleNamespace(create=call)),
    )
    assert embedder.embed(["x"]) == [[0.3]]
    assert call.kwargs["dimensions"] == 1
    assert (embedder.model, embedder.dim) == ("emb", 1)
