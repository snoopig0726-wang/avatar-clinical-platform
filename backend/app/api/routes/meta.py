from fastapi import APIRouter

from app.schemas.meta import ContractMetaResponse

router = APIRouter()


@router.get("/contracts", response_model=ContractMetaResponse)
async def contracts() -> ContractMetaResponse:
    return ContractMetaResponse(
        contract_version="v1",
        prompt_template_version="voice-to-appearance-v1.0",
        roles=["doctor", "invited_patient", "admin"],
        fixed_emotions=[
            "anger",
            "indifference",
            "sarcasm",
            "sadness",
            "fear",
            "commanding",
        ],
        adjustment_limit_per_case=3,
        retention_days_after_archive=30,
        initial_structured_risk_classification=False,
    )
