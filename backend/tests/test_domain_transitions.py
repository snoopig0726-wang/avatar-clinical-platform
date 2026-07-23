import pytest

from app.domain.enums import GenerationStatus, SessionStatus
from app.domain.transitions import (
    GENERATION_TRANSITIONS,
    SESSION_TRANSITIONS,
    InvalidStateTransition,
    assert_transition,
)


def test_patient_pause_requires_doctor_controlled_resume_transition() -> None:
    assert_transition(SessionStatus.ACTIVE, SessionStatus.PAUSED, SESSION_TRANSITIONS)
    assert_transition(SessionStatus.PAUSED, SessionStatus.ACTIVE, SESSION_TRANSITIONS)


def test_ended_session_cannot_resume() -> None:
    with pytest.raises(InvalidStateTransition):
        assert_transition(SessionStatus.ENDED, SessionStatus.ACTIVE, SESSION_TRANSITIONS)


def test_generation_cannot_skip_image_safety_check() -> None:
    with pytest.raises(InvalidStateTransition):
        assert_transition(
            GenerationStatus.GENERATING,
            GenerationStatus.PENDING_DOCTOR_REVIEW,
            GENERATION_TRANSITIONS,
        )
