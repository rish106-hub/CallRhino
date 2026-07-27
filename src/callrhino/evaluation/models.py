from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetSource(EvalModel):
    id: str
    name: str
    platform: Literal["huggingface", "kaggle", "github", "local"]
    url: str
    license: str
    purpose: list[Literal["stt", "extraction", "end_to_end"]]
    indian_context: bool
    real_world_data: bool
    access: Literal["public", "gated", "credentials_required", "local"]
    status: Literal["ready", "blocked", "secondary"]
    limitations: list[str]


class BenchmarkManifest(EvalModel):
    version: str
    sources: list[DatasetSource]


class SttCase(EvalModel):
    id: str
    dataset_id: str
    split: str
    row_index: int
    audio_path: Path
    reference: str
    tags: list[str]
    english_terms: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class SttCaseManifest(EvalModel):
    version: str
    cases: list[SttCase]


class ExpectedDecision(EvalModel):
    text: str
    status: str
    decision_maker_text: str | None = None
    effective_date: date | None = None
    effective_date_text: str | None = None
    date_precision: str
    evidence_segment_ids: list[str] = Field(min_length=1)


class ExpectedAction(EvalModel):
    task: str
    commitment_status: str
    owner_text: str | None = None
    suggested_owner_text: str | None = None
    due_date: date | None = None
    due_text: str | None = None
    deadline_precision: str
    evidence_segment_ids: list[str] = Field(min_length=1)


class ExtractionCase(EvalModel):
    id: str
    title: str
    meeting_date: date
    meeting_type: str = "internal_project"
    transcript: str
    tags: list[str]
    provenance: Literal["synthetic", "public", "consented"]
    expected_decisions: list[ExpectedDecision] = Field(default_factory=list)
    expected_actions: list[ExpectedAction] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)


class ExtractionCaseManifest(EvalModel):
    version: str
    cases: list[ExtractionCase]


class SttPrediction(EvalModel):
    case_id: str
    provider: str
    model: str
    transcript: str
    latency_seconds: float = Field(ge=0)
    audio_duration_seconds: float = Field(gt=0)
    estimated_cost_inr: float = Field(default=0, ge=0)
    error: str | None = None


class ExtractionPrediction(EvalModel):
    case_id: str
    provider: str
    model: str
    latency_seconds: float = Field(ge=0)
    schema_valid: bool
    repaired: bool = False
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    estimated_cost_inr: float = Field(default=0, ge=0)
    brief: dict | None = None
    error: str | None = None


class CandidateKind(StrEnum):
    ACTION = "ACTION"
    DECISION = "DECISION"
    OTHER = "OTHER"


class CandidateCase(EvalModel):
    id: str
    text: str
    label: CandidateKind


class CandidateCaseManifest(EvalModel):
    version: str
    source: str
    provenance: Literal["synthetic", "public", "consented"]
    cases: list[CandidateCase]


class CandidatePrediction(EvalModel):
    id: str
    label: CandidateKind


class CandidatePredictionBatch(EvalModel):
    items: list[CandidatePrediction]
