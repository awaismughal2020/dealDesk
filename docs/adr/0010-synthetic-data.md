# ADR 0010: Synthetic data only

Status: accepted

## Decision
All seeded data and briefs are invented and labelled SAMPLE; organisations in briefs are fictional.
The seed refuses to run unless `APP_ENV=local`. The data is shaped to exercise every path (a thin-
margin role, an over-booked person, an injection brief). Real public tenders may be added manually
by the user; nothing is downloaded.

## Consequences
The demo is safe to share. Figures demonstrate mechanics, not real economics.
