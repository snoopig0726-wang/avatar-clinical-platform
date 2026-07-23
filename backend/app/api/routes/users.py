from fastapi import APIRouter, Depends

from app.api.dependencies import AuthenticatedStaff, get_current_staff
from app.schemas.auth import StaffSummary

router = APIRouter()


@router.get("/me", response_model=StaffSummary)
async def current_user(staff: AuthenticatedStaff = Depends(get_current_staff)) -> StaffSummary:
    return StaffSummary(
        user_id=staff.user.user_id,
        role=staff.user.role,
        display_name=staff.user.display_name or "工作人员",
        email=staff.user.email,
    )
