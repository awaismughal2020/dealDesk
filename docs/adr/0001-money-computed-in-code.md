# ADR 0001: Money is computed in code, never by the model

Status: accepted

## Context
Quotes, margins, VAT and invoice amounts must be exact, explainable and reproducible. Language
models are poor at arithmetic and can be manipulated by text in the brief.

## Decision
All money, margin, dates, capacity and invoice logic lives in `dealdesk.domain`, uses
`decimal.Decimal` (GBP), rounds half-up to pence at line level, and allocates milestones with the
largest-remainder method so parts sum exactly. A test scans the domain for any use of `float`. The
model only proposes hours (validated: known roles, positive, under a ceiling; never clamped) and
writes prose. It never sees rates, prices or margins; in a revision it sees only a code-computed
ranking of role names.

## Consequences
Numbers are deterministic and covered by property-based tests. Prompt injection cannot set a
price. The cost is a little more plumbing to pass structured outputs between model and code.
