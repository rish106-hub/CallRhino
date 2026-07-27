# Compact extraction experiment

Date: 2026-07-27

Branch: `codex/compact-extraction-cost`

## Goal

Reduce provider tokens and cost by asking the model for semantic facts only.
Compile dates, warnings, priorities, evidence strength, and the canonical
`MeetingBrief` locally.

## Design

The model-facing contract contains:

- summary
- topics
- fact kind and state
- actor attribution
- original date phrase
- evidence segment IDs

Python compiles the full meeting record. It also:

- resolves grounded date phrases
- rejects dates absent from cited evidence
- adds missing-owner and missing-deadline warnings
- derives explicit priorities from evidence
- removes exact duplicate facts
- converts generic actors such as `We` to unassigned
- caps output at 2,048 tokens

## Efficiency result

Compared with the canonical `extract-v2.1` run:

| Metric | Canonical | Compact | Change |
|---|---:|---:|---:|
| Prompt plus schema characters | baseline | 28.7% of baseline | 71.3% lower |
| Mean observed cost | ₹0.013341 | ₹0.006899 | 48.3% lower |
| Mean latency | 5.09 s | 3.38 s | 33.6% lower |
| Schema pass | 100% | 100% | unchanged |
| Output ceiling | 4,096 tokens | 2,048 tokens | 50% lower |

OpenAI was not called.

## Accuracy result

The compact prompt did not preserve canonical accuracy:

| Metric | Canonical | Compact |
|---|---:|---:|
| Decision precision | 93.8% | 75.0% |
| Decision recall | 100% | 75.0% |
| Action precision | 81.3% | 53.1% |
| Action recall | 100% | 87.5% |
| Owner accuracy | 100% | 62.5% |
| Classification accuracy | 87.5% | 62.5% |
| Evidence accuracy | 62.5% | 56.3% |
| Forbidden prompt-injection facts | 0 | 0 |

## Decision

Do not merge this branch into the product yet.

The deterministic compiler is useful and should be retained as an experiment.
The compact prompt needs a stronger candidate-selection stage or a better model
before it can replace the canonical extractor. Lower cost is not useful when
false actions enter the review queue.

The `99.5%` target cannot be claimed from eight synthetic cases. It needs a
defined field-level metric, a frozen holdout set, and enough real consented
meetings to produce a meaningful confidence interval.
