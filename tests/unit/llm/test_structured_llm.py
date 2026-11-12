import pytest
from pydantic import BaseModel

from dealdesk.adapters.llm.base import RawCompletion, StructuredLLM, TransientLLMError
from dealdesk.ports.llm import LLMError, PromptSpec

PROMPT = PromptSpec("p", "1.0.0", "system", "user")


class Out(BaseModel):
    value: int


class ScriptedClient:
    provider = "scripted"
    model = "m"

    def __init__(self, *steps: object) -> None:
        self.steps = list(steps)
        self.calls = 0

    def complete(self, prompt: PromptSpec, schema: type[BaseModel]) -> RawCompletion:
        self.calls += 1
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return RawCompletion(str(step), 10, 5)


def make(client: ScriptedClient, retries: int = 2) -> tuple[StructuredLLM, list[float]]:
    sleeps: list[float] = []
    ticks = iter(range(100))
    return StructuredLLM(
        client, max_retries=retries, sleep=sleeps.append, clock=lambda: next(ticks)
    ), sleeps


def test_valid_first_time() -> None:
    llm, sleeps = make(ScriptedClient('{"value": 3}'))
    result = llm.generate(PROMPT, Out)
    assert result.output.value == 3
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.attempts) == (
        10,
        5,
        1,
    )
    assert result.usage.latency_ms == 1000
    assert (result.usage.provider, result.usage.model) == ("scripted", "m")
    assert sleeps == []


def test_transient_errors_back_off_then_succeed() -> None:
    client = ScriptedClient(TransientLLMError("429"), TransientLLMError("503"), '{"value": 1}')
    llm, sleeps = make(client)
    result = llm.generate(PROMPT, Out)
    assert result.usage.attempts == 3
    assert sleeps == [0.5, 1.0]


def test_invalid_json_is_re_asked_and_tokens_summed() -> None:
    llm, _ = make(ScriptedClient('{"value": "x"}', "{}", '{"value": 2}'))
    result = llm.generate(PROMPT, Out)
    assert result.usage.input_tokens == 30
    assert result.usage.attempts == 3


def test_gives_up_after_budget() -> None:
    llm, sleeps = make(ScriptedClient(TransientLLMError("a"), "not json"), retries=1)
    with pytest.raises(LLMError, match=r"schema validation.*2 attempts"):
        llm.generate(PROMPT, Out)
    assert sleeps == [0.5]


def test_last_transient_error_does_not_sleep() -> None:
    llm, sleeps = make(ScriptedClient(TransientLLMError("a")), retries=0)
    with pytest.raises(LLMError, match="transient"):
        llm.generate(PROMPT, Out)
    assert sleeps == []
