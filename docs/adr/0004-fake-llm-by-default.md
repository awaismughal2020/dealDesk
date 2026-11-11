# ADR 0004: A deterministic fake model is the default

Status: accepted

## Decision
`LLM_PROVIDER=fake` by default. The fake reads the same rendered prompts a real model would and
returns schema-valid JSON from simple rules, or replays recorded fixtures exactly (strict mode in
`make eval` fails if a prompt changes without re-recording). It is deliberately naive (it copies
injected bullets) so guardrails are exercised for real.

## Consequences
The system runs with no network and no credentials, and every test is deterministic. Model quality
is not demonstrated by the fake; `make eval-live` runs the same checks against a real provider.
