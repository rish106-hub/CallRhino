from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from callrhino.domain.models import StrictModel


class CompactFactKind(StrEnum):
    DECISION = "decision"
    ACTION = "action"
    QUESTION = "question"
    RISK = "risk"


class CompactFactState(StrEnum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    REVERSED = "reversed"
    COMMITTED = "committed"
    CONDITIONAL = "conditional"
    REQUESTED = "requested"
    BLOCKED = "blocked"
    OPEN = "open"
    RISK = "risk"
    BLOCKER = "blocker"
    DEPENDENCY = "dependency"


class CompactActorBasis(StrEnum):
    EXPLICIT = "explicit"
    GROUP = "group"
    SELF_COMMITMENT = "self_commitment"
    ASSIGNED_AND_ACCEPTED = "assigned_and_accepted"
    GROUP_COMMITMENT = "group_commitment"
    UNASSIGNED = "unassigned"


VALID_STATES = {
    CompactFactKind.DECISION: {
        CompactFactState.CONFIRMED,
        CompactFactState.TENTATIVE,
        CompactFactState.DEFERRED,
        CompactFactState.REJECTED,
        CompactFactState.REVERSED,
    },
    CompactFactKind.ACTION: {
        CompactFactState.COMMITTED,
        CompactFactState.CONDITIONAL,
        CompactFactState.REQUESTED,
        CompactFactState.BLOCKED,
    },
    CompactFactKind.QUESTION: {
        CompactFactState.OPEN,
        CompactFactState.DEFERRED,
    },
    CompactFactKind.RISK: {
        CompactFactState.RISK,
        CompactFactState.BLOCKER,
        CompactFactState.DEPENDENCY,
    },
}


class CompactFact(StrictModel):
    kind: CompactFactKind
    text: str = Field(min_length=1, max_length=1000)
    state: CompactFactState
    actor_text: str | None
    actor_basis: CompactActorBasis
    suggested_actor_text: str | None
    date_text: str | None
    evidence_segment_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_semantics(self) -> "CompactFact":
        if self.state not in VALID_STATES[self.kind]:
            raise ValueError(f"{self.state} is not valid for {self.kind}")
        return self


class CompactExtraction(StrictModel):
    schema_version: Literal["compact-1"]
    summary: str = Field(min_length=1, max_length=1200)
    topics: list[str]
    facts: list[CompactFact]
