---
description: Validate Smart-Freeze datasets, maintain hidden ground truth,
  test calculations, and produce reproducible evaluation results without
  fabricated metrics.
name: testing-data-and-evaluation
---

# Testing, Data and Evaluation

## Purpose

Ensure Smart-Freeze's transaction processing, tracing methods, Consensus
Lien, and investigation signals are tested against appropriate evidence.

## Required workflow

1.  Inspect dataset schemas before writing adapters.
2.  Document what each dataset's fields and labels mean.
3.  Define expected behavior and tests before changing calculations.
4.  Run tests and report actual output; never claim a test passed unless
    it was executed.
5.  Keep evaluation reproducible with fixed seeds and saved
    configuration.

## Dataset handling

-   Preserve original downloaded files unchanged in `data/raw/`.
-   Write normalized data to a separate processed directory.
-   Build dataset-specific adapters rather than forcing incompatible
    datasets into one schema.
-   Do not invent missing account IDs, bank fields, timestamps, amounts,
    or labels.
-   Record provenance and document missing fields.
-   Use Elliptic for supported cryptocurrency graph tasks, not as direct
    bank-account lien ground truth.
-   Use AML datasets only for the tasks their schemas and labels
    support.
-   Clearly distinguish public real-world data, bank-informed synthetic
    data, and project-generated synthetic data.

## Hidden ground truth

-   The synthetic generator may track the source of each amount and its
    remaining source lots.
-   Store ground-truth labels separately from operational accounts and
    transactions.
-   The tracing engine, scoring engine, and production-like pipeline
    must not read hidden ground-truth labels.
-   Evaluation code may read ground truth only after the engine outputs
    have been produced.
-   Add tests that verify this separation.

## Test requirements

Create unit tests for: - Duplicate IDs and malformed records. - Invalid
amounts and missing references. - Balance reconstruction and
conservation. - Direct transfers, split transfers, multiple hops,
partial withdrawals, commingling, and later legitimate deposits. -
Cycles, duplicate paths, missing links, and incomplete histories. - Each
tracing method independently. - Consensus Lien bounds, disagreement,
failed methods, and reproducibility. - Investigation scoring and
explanation-to-evidence consistency.

Use hand-calculated fixtures for core algorithm tests. Do not copy one
algorithm's output as another algorithm's expected answer.

## Evaluation

-   Compare tracing estimates with ground truth only where the
    definitions and assumptions make the comparison valid.
-   Report absolute error and appropriate error rates; handle zero
    denominators explicitly.
-   Measure legitimate funds incorrectly included and suspected funds
    missed separately where the evaluation policy supports those
    measurements.
-   Compare against clearly defined baselines.
-   Report dataset, scenario count, assumptions, limitations, and actual
    measured values.
-   Never fabricate metrics, hardcode charts, or claim production
    accuracy based only on synthetic testing.

## Completion report

List tests executed, pass/fail counts, known coverage gaps, actual
benchmark results, and limitations. If a result is not measured, label
it as unmeasured.