from fastapi import APIRouter

from app.routers.responses import INTERNAL
from app.schemas import Health

router = APIRouter(tags=["Health"])


@router.get(
    "/healthz",
    operation_id="healthCheck",
    summary="Liveness check",
    response_model=Health,
    response_description="The server is up.",
    responses={**INTERNAL},
)
def health_check() -> Health:
    # Liveness only: no database access.
    return Health(status="ok")
