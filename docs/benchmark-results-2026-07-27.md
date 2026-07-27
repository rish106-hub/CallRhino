# CallRhino benchmark results

Date: 2026-07-27

Hardware: Apple M3, 8 GB unified memory.

## Decision

Use Sarvam `saaras:v3` in `codemix` mode for the audio path and Sarvam 105B for
the strict canonical meeting record.

Reject these defaults:

- local Whisper Small 4-bit
- local Whisper Large v3 Turbo Q4
- Sarvam STT `transcribe` mode for code-mixed output
- Sarvam 30B for the full one-pass canonical schema

OpenAI was not called. OpenAI spend was $0.

## STT results

Data: 11 deterministic MUCS-Hinglish test clips from Hugging Face.

| Configuration | Mean WER | Reference token precision | Reference token recall | English-term recall | Repetition | Mean RTF | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sarvam Saaras v3, codemix | 53.3% | 67.2% | 74.9% | 78.0% across 9 eligible clips | 0% | 0.096 | ₹0.642 |
| Sarvam Saaras v3, transcribe | 100.7% | 49.4% | 72.5% | 0% across 9 eligible clips | 0% | 0.110 | ₹0.642 |
| MLX Whisper Large v3 Turbo Q4, forced Hindi | 177.6% | 45.1% | 72.4% | 13.9% across 9 eligible clips | 9.1% | 0.255 | ₹0 |
| MLX Whisper Small 4-bit, auto | 302.7% | not rescored | not rescored | 18.2% in the original scorer | 45.5% | 0.221 | ₹0 |

WER is partly inflated by dataset alignment noise. Several audio clips contain
extra adjacent speech that is absent from the row transcript. Token precision
and recall are reported to expose this. The problem does not make the current
STT result release-ready.

Entity recall is not reported because the sampled references contained no
labelled entity phrases. Reporting 100% on zero eligible cases would be false.

## Extraction results

Data: eight synthetic Indian meeting regression cases covering:

- Hinglish self-commitment
- unaccepted assignment
- decision reversal
- vague deadline
- prompt injection
- Tamil-English code mixing
- Indian currency and dates
- proposal-versus-decision negative control

Three Sarvam 105B runs exposed material run-to-run variance. The strongest
`extract-v2.1` run, rescored after correcting the operational-decision label,
produced:

| Metric | Result |
|---|---:|
| Schema pass | 100% |
| Decision precision | 93.8% |
| Decision recall | 100% |
| Action precision | 81.3% |
| Action recall | 100% |
| Owner accuracy | 100% |
| Status accuracy | 87.5% |
| Decision-date accuracy | 100% |
| Deadline accuracy | 100% |
| Evidence accuracy | 62.5% |
| Forbidden prompt-injection facts | 0 |
| Mean latency | 5.09 seconds |
| Total cost for 8 cases | ₹0.107 |

The final `extract-v2.2` run added stricter over-extraction and attribution rules.
It improved the reversal and duplicate-deadline-request cases, but one tiny case
ran to the provider's 4,096-token output limit. That run had 87.5% schema pass,
₹0.166 total cost, and no forbidden prompt-injection facts. This variance means
one good run cannot be treated as a release claim.

The follow-up canonical integration added a single shared retry allowance for
truncated generation or invalid application output. A targeted rerun of the
failed Tamil-English case returned a valid schema for ₹0.0139. Replacing only
the failed case in the saved eight-case result produced these diagnostic
metrics after the matcher was corrected to recognize evidence-grounded
paraphrases:

| Metric | Diagnostic result |
|---|---:|
| Schema pass | 100% |
| Decision precision | 100% |
| Decision recall | 87.5% |
| Action precision | 100% |
| Action recall | 100% |
| Owner accuracy | 93.8% |
| Status accuracy | 93.8% |
| Decision-date accuracy | 87.5% |
| Deadline accuracy | 87.5% |
| Evidence accuracy | 50% |
| Forbidden prompt-injection facts | 0 |
| Estimated cost for the combined current path | ₹0.104 |

This was not a fresh eight-case provider run. It combines seven saved outputs
with one targeted rerun and must not be presented as release validation.

`extract-v2.3` added explicit operational-decision rules. A fresh provider run
then passed all eight schemas without repair. Its outputs were replayed through
the finalized deterministic evidence and normalization layer after the provider
run. The resulting development-set diagnostic was:

| Metric | Result |
|---|---:|
| Schema pass | 100% |
| Decision precision and recall | 100% each |
| Action precision and recall | 100% each |
| Owner accuracy | 100% |
| Status accuracy | 100% |
| Decision-date accuracy | 100% |
| Deadline accuracy | 100% |
| Evidence accuracy | 100% |
| Forbidden prompt-injection facts | 0 |
| Mean latency | 4.16 seconds |
| Total provider cost | ₹0.118 |

The local layer completed context for reversals, deferrals, terse approvals,
requested actions, and pronoun-based commitments. It also removed duplicate
operational actions, same-owner commitment decisions, stale warnings, and an
unsupported decision date. One development gold label was corrected to include
the segment that established finance approval.

This is regression evidence on eight inspected synthetic cases. It is not a
holdout result and does not support a `99.5%` production claim.

Current weaknesses:

- provider output still shows run-to-run variance
- the development set is small and prompt-visible
- long-meeting candidate gating has no independent recall result
- positive end-to-end real meeting audio is still missing

Local deterministic normalization now resolves the supported date phrases,
removes stale deadline warnings, strips unsupported priority guesses, and rejects
generic attributions such as `We`. It does not invent tasks, owners, or decisions.

An experimental local candidate gate reduced a constructed 100-segment
transcript to 12 segments and reduced total prompt characters by 44%. It remains
disabled by default because this cost reduction has not passed a long-meeting
recall holdout.

Sarvam 30B hit the 4,096-token output limit on the full schema for tiny
three-line meetings. It is not the canonical extractor.

## Compact candidate stage

Data: 90 balanced synthetic English snippets from the Kaggle Teams Meeting
Transcripts dataset.

Sarvam 30B at a batch size of 10:

- accuracy: 100%
- macro F1: 100%
- latency: 11.2 seconds for 9 requests
- cost: ₹0.034

A batch size of 30 failed ID-completeness validation. The 100% score is on an
easy synthetic set and must not be treated as production evidence.

## End-to-end control

The 11 public MUCS-Hinglish clips were transcribed with Saaras codemix, combined
as a non-meeting technical tutorial, and extracted with Sarvam 105B.

Both the gold transcript and STT transcript produced:

- valid canonical schema
- 0 decisions
- 0 actions
- 0 open questions
- 0 risks

Total extraction cost was ₹0.032. This proves the negative path only. A positive
end-to-end benchmark still requires consented Indian meeting audio with human
annotations.

## Data sources

- [MUCS-Hinglish](https://huggingface.co/datasets/dianavdavidson/MUCS-Hinglish), CC BY 4.0
- [Kathbath](https://huggingface.co/datasets/ai4bharat/Kathbath), gated
- [LAHAJA](https://huggingface.co/datasets/ai4bharat/Lahaja), gated
- [Kaggle Teams Meeting Transcripts](https://www.kaggle.com/datasets/yusufayta/teams-meeting-transcripts), secondary synthetic data
- [QMSum](https://github.com/Yale-LILY/QMSum), later long-context benchmark
- [AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/), later real-meeting benchmark

## Current limit

There is no honest claim of comprehensive Indian meeting accuracy yet. The next
required asset is a small consented benchmark with 20 real meetings, at least:

- 8 Hindi-English
- 4 English with Indian accents
- 2 Tamil-English
- 2 Telugu-English
- 2 noisy or remote calls
- 2 overlapping-speaker calls

Each meeting needs human-reviewed transcript segments, decisions, actions,
owners, deadlines, and evidence IDs.
