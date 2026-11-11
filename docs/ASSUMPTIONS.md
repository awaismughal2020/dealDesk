# Assumptions

## All data is synthetic

Every seeded record is SAMPLE data invented for this demo: the rate card, the ten-person roster,
the five past projects and their case studies, and the three briefs. The organisations named in the
briefs ("Northfield Homes", "Harbourside Mutual") are fictional. No real company's rates, people,
clients or outcomes appear anywhere, and nothing describes any real organisation.

The sample data is shaped to exercise the product honestly:

- One role (a contract ML specialist) has a thin margin, so an AI-heavy brief falls below the
  minimum margin and the revision loop runs.
- One sample UX designer has 12 hours a week, so the clean brief produces a visible resource clash.
- Most roles sit around 33 to 37% margin, so typical quotes land just below the 35% target and the
  "price needed for target margin" is shown.

## Commercial policy (configurable in `.env`)

| Setting | Default | Meaning |
| --- | --- | --- |
| `CONTINGENCY` | 0.10 | Added to hours, not money |
| `TARGET_MARGIN` | 0.35 | Below this, the target price and gap are shown |
| `MINIMUM_MARGIN` | 0.25 | Below this, the quote is flagged and the estimate revised (max 2) |
| `VAT_RATE` | 0.20 | UK standard rate, shown separately |
| `INVOICE_MILESTONE_PERCENTAGES` / `_OFFSET_DAYS` | 30,40,30 / 0,42,84 | Milestones and due dates from the start date |
| `PROJECT_WEEKS` | 12 | Weeks the hours are spread over |
| `START_DATE_LEAD_DAYS` | 14 | Planned start is the first Monday at least this far ahead |

## Savings figures are targets to be measured, not results

The impact panel compares 40 hours by hand per bid (extraction 4, estimate and costing 8, resource
check 4, proposal first draft 20, pipeline and invoice setup 4) with assisted time (measured machine
time plus human review time: 0.5, 1.5, 0.5, 4 and 0.25 hours). With 60 bids a year, £75 per hour,
1,650 working hours per FTE and 60% of saved time becoming cash, the defaults show about 1,995 hours,
1.21 FTE and £149,625 a year (£89,775 cashable).

**Every one of those inputs is an assumption.** None was measured. They are targets for a pilot,
where real baselines and review times would replace them. The panel says so on screen, and every
input can be changed.

## The fake model

The default model is deterministic and rule-based. It reads the same prompts a real model would and
returns schema-valid JSON, but its extraction is pattern matching (bullets and "shall/must" lines)
and its estimate scales the most similar past project by requirement count. It exists so the whole
system runs offline and testably; it is not evidence of model quality. `make eval-live` runs the
same checks against a real provider.

## Other working assumptions

- Runs are visible to every signed-in role (the specification grants read access to all roles).
- Machine time in the impact panel is the mean measured duration of completed workflow steps; with
  the fake model it is close to zero.
- Embeddings are 256-dimensional to match the database schema; real providers are asked for 256.
