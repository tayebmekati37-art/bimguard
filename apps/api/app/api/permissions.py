from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.permissions import PermissionsOut
from app.services.permissions import capabilities_for

router = APIRouter(tags=["auth"])


@router.get("/me/permissions", response_model=PermissionsOut)
def my_permissions(user: User = Depends(get_current_user)) -> PermissionsOut:
    """Report what the current role can do. Lets the frontend hide controls
    the backend would reject anyway."""
    return PermissionsOut(
        role=user.role.value,
        capabilities=capabilities_for(user.role.value),
    )