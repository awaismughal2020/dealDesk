# ADR 0006: One structured-generation path for every model provider

Status: accepted

## Decision
`LLMPort.generate(prompt, schema)` returns a validated Pydantic object. Provider adapters implement
a minimal `ModelClient.complete()` that returns JSON text and token counts using each SDK's
structured output: Google Gen AI SDK on Vertex AI (`response_json_schema`), Anthropic
(`messages.parse(output_format=...)`) and OpenAI (`responses.parse(text_format=...)`). One wrapper
(`StructuredLLM`) owns timeouts, bounded backoff, schema re-asks and token accounting for all.
Provider and model names come only from configuration; SDKs are imported only when selected.

## Consequences
Behaviour is identical across providers and the fake. The installed Anthropic SDK (2.x) does not
accept a sampling temperature on these calls, so none is sent for Anthropic (verified against the
installed SDK, not assumed). Real adapters are unit-tested with stubbed SDK clients; they were not
exercised against live services while building.
