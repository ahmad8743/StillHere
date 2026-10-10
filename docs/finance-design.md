# StillHere — Recovery Finance Design

Status: supporting financial design. The consolidated [project specification](project-specification.md) controls scope and resolves implementation defaults.

Updated: October 10, 2026.

## Purpose and challenge fit

StillHere's financial feature should help a household answer three questions: What money can I actually use? When will my listed essential expenses become unaffordable? Which feasible recovery action improves that outlook?

The user clarified that Flex integration is not required. The goal is an innovative fintech feature for the Best FinTech App category. The published challenge describes creative use of fintech without specifying a required provider or API. This proposal's competition argument is financial planning technology adapted to disaster recovery; judging eligibility and awards remain the organizers' decision. [Challenge criteria](https://www.hackmidwest.com/).

The MVP is a working recovery cash-flow planner integrated with the prerequisite planner. Manual inputs must work for a cash-only household. The consolidated specification sets read-only Plaid Sandbox linking as an optional stretch feature. No Flex dependency remains.

## 1. Core product experience

### Available resources

Show resources in distinct groups rather than one inflated balance:

- Accessible cash and bank funds, with source and as-of time.
- Money that exists but is currently inaccessible, such as an account the user cannot access.
- Received restricted assistance, with known permitted uses and expiry where applicable.
- Confirmed noncash support, such as meals, shelter, or transport for stated dates.
- Future income and aid, with amount, stage, source, and timing uncertainty.

Credit limits, unsold possessions, application amounts, and noncash support do not become spendable cash. Existing bills can be recorded as obligations; a new borrowing or payment capability is outside this MVP.

### Essential-expense forecast

Provide a dated 14-day forecast. Ask progressively for relevant expenses rather than demanding a complete financial profile before displaying help. The user can enter recurring daily costs and dated one-time costs for essentials and recovery actions.

Display:

- Money accessible now.
- The first projected date when a listed essential expense cannot be covered.
- The amount of the projected gap on that date.
- Upcoming recovery costs and their effect on the forecast.
- Assumptions, missing costs, and stale balances.

This is coverage of the entered expense schedule, not a prediction of how long a person can survive. When necessary facts are missing, show a partial estimate and the questions that would make it more useful.

### Aid timing and scenarios

Maintain an aid tracker: discovered, eligibility unknown or checked, preparing, applied, approved, received, denied, or appeal in progress. Each status is attributed to a user report or provider evidence. An imported deposit does not prove the identity or terms of an award.

The baseline excludes unreceived aid. Compare up to three bounded alternatives against it, such as a stated award arriving on day 8, arriving on day 12, or failing to arrive within the forecast. Show assumptions explicitly; do not invent award probabilities or delivery dates.

Restricted funds pay only compatible expenses. When restrictions are unknown, keep the funds separate and request clarification. Noncash support reduces only the expense it actually covers, for its confirmed dates and household coverage. Suggested resources appear in a scenario until the user confirms access. Overlapping resources must not erase the same expense twice.

### Financial effects of recovery steps

Each next step can carry known fees, travel costs, childcare costs, and timing. Unknown amounts stay unknown. Compare a small set of source-supported paths, such as an in-person application versus an available remote process or a documented fee waiver.

For each path, show requirements, accessibility, dates, immediate cost, and effect on the 14-day forecast. The prerequisite planner rejects infeasible paths before financial comparison. Safety, necessary care, deadlines, and user priorities take precedence over minimizing cost; the system must not improve a forecast by silently dropping essential needs.

After a change in finances, the agent can look for suitable resources or lower-cost recovery paths and update the next steps. It never treats a suggested saving as realized, guarantees assistance, or spends money automatically.

## 2. Dashboard and conversation

Use a small set of fixed components:

| Component | What the user can do |
| --- | --- |
| Available money | Add or correct cash and accessible balances; mark funds inaccessible |
| 14-day expense outlook | Edit an expense; inspect the first uncovered need and its assumptions |
| Aid tracker | Update an application or receipt; see restricted and uncertain amounts separately |
| Compare options | Compare baseline with aid timing, confirmed resources, or an alternative action |
| Financial next step | Open a relevant resource, change a recovery step, or explain a blocker |

Conversational entries such as "I spent $18 today" become structured proposed financial events with amount, date, affected money source, and any unresolved detail. The interface shows the interpretation and offers correction before an ambiguous entry changes authoritative state. Explicit dashboard entries use the same ledger service. Corrections remain auditable and can be undone.

Recalculate when an expense, balance, receipt, aid status, resource confirmation, or selected recovery action changes. Reassess on return to the application. Background bank monitoring and proactive notifications are later capabilities unless separately selected; the prototype does not promise that a closed or offline application is continuously watching finances.

## 3. High-level architecture

```text
Manual entries / optional read-only bank adapter
                       |
             Validated financial records
                       |
             Deterministic forecast engine
                  /               \
        Dashboard results     Strands agent tools
                                     |
                         Prerequisite / recovery planner
                                     |
                         Source-backed alternatives
```

The same private recovery file supplies chat and dashboard state. Qwen interprets the user's circumstances and explains alternatives. Application code calculates money, applies restrictions, validates financial updates, and persists changes.

### Financial records

Define these logical records; the later implementation sessions choose storage and exact schemas:

- **Money source:** cash or account identifier, accessible amount, availability constraints, source, currency, and as-of time.
- **Financial event:** stable ID, amount, direction, event date, money source, actual or proposed status, provenance, and optional aid/task link.
- **Expense commitment:** category, amount or unknown amount, date or recurrence, essential status, user confirmation, and link to a recovery step where applicable.
- **Aid item:** program, lifecycle stage, amount, restrictions, timing evidence, application link, and matching receipt where known.
- **Support coverage:** the expense covered, dates, quantity or value limit, access confirmation, and evidence.
- **Scenario:** explicit differences from the baseline, plus the case version used for calculation.
- **Forecast:** dated results, first uncovered expense, gap amounts, assumptions, and input version.

Use integer cents and USD for the MVP. Financial events must be idempotent so retries and offline synchronization do not duplicate expenses or receipts.

### Forecast contract

Anchor a forecast in an accessible balance as of a known time. Apply only events not already reflected in that balance, then subtract future expense commitments. A record of historical spending is not a reason to deduct it again from the current balance.

Keep unrestricted cash and each restricted balance separate. Apply confirmed support coverage to eligible expenses first, then eligible restricted funds, then unrestricted cash, using a documented allocation order and user priorities. The implementation should expose unmet expenses rather than represent a negative projection as actual borrowed money.

For a simple unrestricted case:

```text
projected_position(day) = opening_accessible_money
                        + included_receipts_through_day
                        - uncovered_expenses_through_day
```

Actual spending must reconcile with its corresponding forecast commitment rather than counting both as additional spending. A receipt marked received and a matching imported deposit represent one receipt. Pending and posted records can also represent one transaction. Internal transfers and cash withdrawals change the location of money, not household income; fees are separate outflows.

A refreshed account balance must not be combined with already included transactions to fabricate a second deduction. If an imported snapshot cannot be reconciled with manual entries, preserve both sources, mark the conflict, and ask for a current accessible balance. Do not resolve an uncertain match by silently overwriting the user's cash record.

### Agent tool responsibilities

| Conceptual tool | Responsibility |
| --- | --- |
| Read financial summary | Return necessary balances, commitments, aid states, and uncertainties |
| Propose/record financial update | Validate a user-authorized entry and persist it once |
| Calculate forecast | Produce a reproducible 14-day baseline and uncovered expenses |
| Compare scenarios | Evaluate explicit proposed changes without modifying the baseline |
| Evaluate action costs | Return financial consequences for feasible recovery paths |
| Update financial dashboard | Publish structured components from persisted records and calculations |

Tool permissions scope every read and write to the household. Bank credentials and provider access tokens never enter the model conversation. Give the agent the minimum necessary financial summary; household transactions do not enter shared program knowledge.

## 4. Optional fintech API demonstration

If bank connectivity is selected, use a read-only Plaid Sandbox integration to demonstrate account linking and transaction ingestion. Plaid documents sandbox test accounts and simulation tools; this is synthetic bank data, not real survivor accounts. Sandbox balances and transactions can be inconsistent across products, so use a deliberate custom fixture or show unresolved discrepancies rather than forcing a misleading reconciliation. [Sandbox documentation](https://plaid.com/docs/sandbox/).

Proposed flow: user chooses to link a test account; the bank-linking interface completes; the backend stores the provider token privately; an adapter imports selected balances and transaction changes; normalized records enter the same finance service; forecasts and relevant recovery steps update. A manual cash balance remains independently available.

Plaid's Transactions documentation describes `/transactions/sync`, added/modified/removed records, saved cursors, and webhook-driven updates. Freshness must be visible; imported history does not automatically predict the household's new disaster-related spending. [Transactions documentation](https://plaid.com/docs/transactions/). Balance selection and availability also require separate treatment. [Balance documentation](https://plaid.com/docs/balance/).

Bank linking is an input convenience and a technical demonstration. The financial planning capability remains useful when the household has no account, cannot authenticate, declines linking, or loses connectivity. Production provider access, fees, institutional coverage, consent, secure token lifecycle, and reliable ongoing synchronization require later validation. No payment API is required for the recommended scope.

## 5. Demonstration scenario

All figures and resource arrangements below are synthetic demonstration assumptions, not real aid offers or agency policies. Day 1 is the first forecast day; daily expenses are paid on each day.

A mother with two children has $300 accessible cash. Her entered expenses are $20/day for food, $40/day for temporary lodging, $5/day for transport, and a one-time $30 recovery expense on day 1.

| Scenario | First projected gap | What it demonstrates |
| --- | --- | --- |
| Baseline, no new support or aid | Day 5; $55 unmet that day | Costs are dated; $300 is not treated as enough for the entire recovery plan |
| Confirmed food and shelter coverage for days 1–7 | Day 11; $25 unmet that day | Noncash support reduces eligible costs rather than increasing cash |
| Same coverage; hypothetical $500 aid receipt on day 8 | No gap in the 14-day forecast; $280 projected at day 14 | The receipt scenario is explicitly conditional |
| Same coverage; hypothetical $500 receipt delayed to day 12 | Day 11; $25 gap, despite $280 projected at day 14 | The same final balance can conceal an earlier unmet essential need |

The agent explains the day-11 gap and finds a source-supported action that could cover it or change the route. It also adapts when the user reports no car: available remote procedures or verified transport alternatives affect prerequisites and costs together. In a real case, confirmed dates and costs are required before an option becomes part of the baseline.

Then record an actual expense or an aid receipt, update the case once, recalculate, and revise only affected steps. If bank linking is implemented, repeat the financial update with labeled sandbox data and demonstrate duplicate handling.

## 6. Implementation scope and ownership

Required proposal: manual accessible balances, essential-expense schedule, aid lifecycle, known restricted/noncash support, deterministic 14-day forecasts, scenario comparison, recovery-action costs, shared chat/dashboard state, and finance-triggered replanning. Start with a bounded number of records and paths; a nationwide benefits optimizer is not required.

Proposed stretch: read-only sandbox bank linking after the core journey works. Defer receipt OCR, an identity-document vault, automatic benefit-award prediction, new lending, money movement, automatic bill negotiation, full production bank onboarding, and background notifications.

Suggested later coding-agent responsibilities:

1. Finance service: record validation, reconciliation, forecast/scenario calculations, and financial correctness checks.
2. Agent/planner integration: financial tools, feasible alternatives, and plan revisions after financial changes.
3. Dashboard: accessible money, forecast, scenario, and aid controls using the shared case contracts.
4. Optional data adapter: sandbox linking and imports, with explicit labels, source timing, disconnect, and reconciliation.

Agree shared record and tool contracts before these work packages run in parallel. This document assigns no agents and starts no implementation.

## 7. Acceptance evidence

- Reproduce every value in the demonstration table with code.
- Approved but unreceived aid changes a scenario without increasing accessible cash.
- Restricted food assistance cannot cover rent, and overlapping support does not double-count savings.
- An early gap remains visible even when a later receipt yields a positive final balance.
- Repeated event delivery, offline replay, and an aid/deposit match each create one financial effect.
- Actual spending and its budget commitment do not create two outflows.
- Missing costs, inaccessible money, stale balances, and conflicting imports are visible.
- Changing an expense or transport constraint affects the forecast and relevant steps while preserving completed work.
- If the optional adapter exists, imported pending/posted updates and removed transactions reconcile correctly, and API failure leaves manual use available.
