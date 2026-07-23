from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from app.domain.enums import (
    AdjustmentStatus,
    CaseStatus,
    GenerationStatus,
    SessionStatus,
)


class InvalidStateTransition(ValueError):
    def __init__(self, current: StrEnum, target: StrEnum):
        super().__init__(f"invalid state transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


CASE_TRANSITIONS: Mapping[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.DRAFT: frozenset({CaseStatus.IN_PROGRESS, CaseStatus.ARCHIVED}),
    CaseStatus.IN_PROGRESS: frozenset({CaseStatus.COMPLETED, CaseStatus.ARCHIVED}),
    CaseStatus.COMPLETED: frozenset({CaseStatus.IN_PROGRESS, CaseStatus.ARCHIVED}),
    CaseStatus.ARCHIVED: frozenset({CaseStatus.DRAFT}),
}

SESSION_TRANSITIONS: Mapping[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.WAITING_DOCTOR: frozenset(
        {SessionStatus.ACTIVE, SessionStatus.ENDED, SessionStatus.EXPIRED}
    ),
    SessionStatus.ACTIVE: frozenset(
        {SessionStatus.PAUSED, SessionStatus.ENDED, SessionStatus.EXPIRED}
    ),
    SessionStatus.PAUSED: frozenset(
        {SessionStatus.ACTIVE, SessionStatus.ENDED, SessionStatus.EXPIRED}
    ),
    SessionStatus.ENDED: frozenset(),
    SessionStatus.EXPIRED: frozenset(),
}

GENERATION_TRANSITIONS: Mapping[GenerationStatus, frozenset[GenerationStatus]] = {
    GenerationStatus.QUEUED: frozenset(
        {GenerationStatus.GENERATING, GenerationStatus.CANCELLED, GenerationStatus.FAILED}
    ),
    GenerationStatus.GENERATING: frozenset(
        {GenerationStatus.CHECKING, GenerationStatus.CANCELLED, GenerationStatus.FAILED}
    ),
    GenerationStatus.CHECKING: frozenset(
        {
            GenerationStatus.PENDING_DOCTOR_REVIEW,
            GenerationStatus.CANCELLED,
            GenerationStatus.FAILED,
        }
    ),
    GenerationStatus.PENDING_DOCTOR_REVIEW: frozenset(
        {GenerationStatus.APPROVED, GenerationStatus.REJECTED}
    ),
    GenerationStatus.APPROVED: frozenset(),
    GenerationStatus.REJECTED: frozenset(),
    GenerationStatus.FAILED: frozenset(),
    GenerationStatus.CANCELLED: frozenset(),
}

ADJUSTMENT_TRANSITIONS: Mapping[AdjustmentStatus, frozenset[AdjustmentStatus]] = {
    AdjustmentStatus.PENDING_DOCTOR_REVIEW: frozenset(
        {
            AdjustmentStatus.APPROVED_AS_IS,
            AdjustmentStatus.APPROVED_EDITED,
            AdjustmentStatus.REJECTED,
        }
    ),
    AdjustmentStatus.APPROVED_AS_IS: frozenset(
        {AdjustmentStatus.GENERATING, AdjustmentStatus.CANCELLED}
    ),
    AdjustmentStatus.APPROVED_EDITED: frozenset(
        {AdjustmentStatus.GENERATING, AdjustmentStatus.CANCELLED}
    ),
    AdjustmentStatus.GENERATING: frozenset(
        {AdjustmentStatus.APPLIED, AdjustmentStatus.GENERATION_FAILED, AdjustmentStatus.CANCELLED}
    ),
    AdjustmentStatus.REJECTED: frozenset(),
    AdjustmentStatus.APPLIED: frozenset(),
    AdjustmentStatus.GENERATION_FAILED: frozenset(),
    AdjustmentStatus.CANCELLED: frozenset(),
}


def assert_transition(
    current: StrEnum,
    target: StrEnum,
    transitions: Mapping[StrEnum, frozenset[StrEnum]],
) -> None:
    if target not in transitions.get(current, frozenset()):
        raise InvalidStateTransition(current, target)
