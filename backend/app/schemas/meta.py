from pydantic import BaseModel, Field


class ContractMetaResponse(BaseModel):
    contract_version: str
    prompt_template_version: str
    roles: list[str]
    fixed_emotions: list[str] = Field(min_length=6, max_length=6)
    adjustment_limit_per_session: int
    retention_days_after_archive: int
    initial_structured_risk_classification: bool
