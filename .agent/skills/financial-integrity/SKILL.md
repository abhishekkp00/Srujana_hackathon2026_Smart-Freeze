---
description: Build Smart-Freeze's validated transaction ledger, fund-flow
  graph, proportional tracing, FIFO, LIBR, and Consensus Lien with
  precise arithmetic and explicit assumptions.
name: financial-integrity-and-fund-tracing
---

# Financial Integrity and Fund Tracing

## Purpose

Implement Smart-Freeze's core financial processing and fund-tracing logic
accurately, transparently, and reproducibly.

## Required workflow

1.  Inspect the existing repository and current implementation before
    editing.
2.  State the task, files to change, assumptions, and acceptance
    criteria.
3.  Implement only the current requested phase; do not jump ahead to the
    UI.
4.  Add or update tests with each behavioral change.
5.  Run the relevant tests and report actual results.

## Financial data integrity

-   Represent INR amounts internally as integer paise or use an
    appropriate exact decimal type. Never use binary floating-point for
    exact currency calculations.
-   Validate transaction IDs, timestamps, amount signs, account
    references, case references, and transaction direction.
-   Explicitly model deposits, withdrawals, transfers, reversals, and
    opening balances.
-   Preserve raw source references and record data-quality warnings.
-   Never silently invent missing transactions, repair inconsistent
    balances, or interpret missing data as zero.
-   Make transaction ordering deterministic, including a documented
    tie-breaker for equal timestamps.
-   Avoid double-counting transactions or overlapping claims.

## Transaction graph

-   Represent accounts as nodes and transfers as directed, timestamped
    edges.
-   Preserve transaction IDs and amounts on edges.
-   Handle split transfers, multiple hops, cycles, duplicate paths, and
    incomplete histories.
-   Graph connectivity indicates a possible path; it does not prove that
    the same funds remain in a downstream account.

## Tracing methods

Implement proportional tracing, FIFO, and the Lowest Intermediate
Balance Rule (LIBR) as separate modules with independent tests. -
Document the precise convention and assumptions used by each method. -
Define handling for commingling, withdrawals, later deposits, fees,
reversals, incomplete history, and competing claims. - Do not assume
simplified implementations automatically match every legal or
jurisdictional tracing rule. - Keep tracing logic independent from UI
code and investigation scoring.

## Consensus Lien

For valid outputs from the same account, case, ledger version, and
compatible scope: - Lower estimate = minimum of the method outputs. -
Upper estimate = maximum of the method outputs. - Disagreement = upper
estimate minus lower estimate.

If a method fails or required history is missing, expose the limitation;
do not silently present an incomplete comparison as a complete
three-method result. These are method-dependent estimates, not a legal
conclusion or proof of recoverable funds.

## Prohibited shortcuts

-   Never hardcode outputs that should be calculated.
-   Never fabricate test results, transaction evidence, or accuracy
    claims.
-   Never call a score or tracing estimate proof of guilt.
-   Never implement automatic account freezing or case closure.

## Completion report

At the end of each task, list files changed, commands executed, actual
test results, assumptions, unresolved issues, and the next smallest
step.