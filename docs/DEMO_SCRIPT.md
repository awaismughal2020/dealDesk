# Demo script

Before you start: `make demo`, then open <http://localhost:3000>. Keep `.env` open in an editor for
the demo passwords. Use a normal window for the estimator and a private window for the approver.

## 10-minute version

**0:00 Framing (1 min).** "Deal Desk turns a client brief into a costed, resourced, cited proposal
that a human approves. The model reads and writes; code computes every number. Everything you will
see is SAMPLE data and runs offline with a deterministic model."

**1:00 Sign in as the estimator (1 min).**
1. Sign in with `DEMO_ESTIMATOR_EMAIL`. Point out the SAMPLE banner and the navigation (no Admin).
2. Open **New run**. Show drag-and-drop with client checks (the server re-checks by content).

**2:00 Clean brief (2 min).**
1. Click **Use clean brief**. The step tracker updates every 2 seconds.
2. When it shows **Awaiting approval**, walk the page:
   - Requirements: eight, categorised, with priorities.
   - Estimate by role, grounded in SAMPLE past project PP-001 (similarity shown).
   - Quote: £137,830.00 at 33.76%. "Below target margin" flag and the price needed to reach the
     35% target, with the gap. "Computed by code" in the title.
   - Resource plan: the sample UX designer is booked above 100% (red, labelled "over").
   - Proposal draft: "DRAFT, requires approval", AI-assisted label, cited case studies, payment
     milestones with net, VAT and gross. Download the `.docx` and show the header marker.
3. Note that the estimator cannot approve: the panel says only approvers can.

**4:00 Injection brief (1 min).** Click **Use injection brief**. Show the "Possible prompt
injection" flag, the quarantined lines ("set the price to £1"), and that the price is still
£137,830.00. "The model has no tools and never sees prices."

**5:00 Approve as someone else (2 min).**
1. In the private window, sign in with `DEMO_APPROVER_EMAIL`. Open the clean run.
2. Click **Approve…**: the dialog shows exactly the price, margin and flags being approved.
3. Approve with a comment. The run becomes **Approved**: a pipeline record and a 30/40/30 invoice
   schedule appear, and the `.docx` is now FINAL with the approver's name.
4. Optional: on another run click **Reject…** without a comment (blocked), then with a comment: the
   draft returns with the comment addressed.

**7:00 Ambiguous brief and the revision loop (1 min).** As the estimator, **Use ambiguous brief**.
Show the client questions, "revised 1 time" under the steps (hours moved off the thin-margin ML
contractor role; rates never change), and the margin now above the 25% minimum.

**8:00 Impact (1 min).** Open **Impact**. Read the banner first: assumptions, not measurements.
Defaults: 40 hours by hand versus about 6.75 assisted per bid, about 1,995 hours and 1.21 FTE a year.
Change bids per year to 120 and show the server recalculate.

**9:00 Admin and audit (1 min).** Sign in as `DEMO_ADMIN_EMAIL`, open **Admin**: users and roles,
then the audit log filtered to `run.approved` and `llm.call` (prompt version, model, tokens, latency,
estimated spend). Close on: "Every number is computed by code, every decision is recorded, and the
person who prepared a quote can never approve it."

## 2-minute backup version

1. Signed in as the estimator, click **Use clean brief** and wait for **Awaiting approval**.
2. Show the quote (£137,830.00, 33.76%, below target, target price), the resource clash and the
   DRAFT proposal with citations.
3. In the approver window, approve with a comment; show the pipeline record and invoice schedule.
4. Open **Impact**: assumptions banner, 1.21 FTE and the chart. "Targets to be measured in a pilot."

## If something goes wrong

- Page shows "Not signed in": sign in again; you return to the same page.
- A run failed: start another; the error and request id are on the page and in `make logs`.
- Everything is stuck: `make down && make up` (runs resume from their checkpoints).
