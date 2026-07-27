from decimal import Decimal

import pytest
from pydantic import ValidationError

from callrhino.config import Settings


def test_openai_key_does_not_enable_fallback_by_itself() -> None:
    settings = Settings(OPENAI_API_KEY="test_key", _env_file=None)

    assert settings.has_openai_credentials
    assert not settings.openai_fallback_active
    assert settings.openai_hard_budget_usd == Decimal("1.50")


def test_openai_fallback_requires_key_and_explicit_flag() -> None:
    settings = Settings(
        OPENAI_API_KEY="test_key",
        OPENAI_FALLBACK_ENABLED=True,
        _env_file=None,
    )

    assert settings.openai_fallback_active


def test_openai_hard_budget_cannot_exceed_project_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(OPENAI_HARD_BUDGET_USD="1.51", _env_file=None)


def test_openai_soft_budget_cannot_exceed_hard_budget() -> None:
    with pytest.raises(ValidationError):
        Settings(
            OPENAI_SOFT_BUDGET_USD="1.26",
            OPENAI_HARD_BUDGET_USD="1.25",
            _env_file=None,
        )


def test_sarvam_output_cap_cannot_exceed_provider_guardrail() -> None:
    with pytest.raises(ValidationError):
        Settings(SARVAM_MAX_OUTPUT_TOKENS=4097, _env_file=None)
