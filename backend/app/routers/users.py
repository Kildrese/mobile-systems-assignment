from fastapi import APIRouter, Response, status

from app import models, schemas
from app.deps import Db, OwnUserId
from app.errors import NOT_FOUND as NOT_FOUND_ERROR
from app.routers.responses import BAD_REQUEST, INTERNAL, NOT_FOUND, UNAUTHORIZED, conflict
from app.services import accounts

router = APIRouter(prefix="/api/users", tags=["Users"])

# Users may only touch their own account; `OwnUserId` answers 404 for any
# other id before the handler runs.


@router.get(
    "/{id}",
    operation_id="getUser",
    summary="Read your own user",
    response_model=schemas.User,
    response_description="The user.",
    responses={**UNAUTHORIZED, **NOT_FOUND, **INTERNAL},
)
def get_user(db: Db, user_id: OwnUserId):
    user = db.get(models.User, user_id)
    if user is None:
        raise NOT_FOUND_ERROR
    return user


@router.patch(
    "/{id}",
    operation_id="updateUser",
    summary="Update your own username or name",
    response_model=schemas.User,
    response_description="The updated user.",
    responses={
        **BAD_REQUEST,
        **UNAUTHORIZED,
        **NOT_FOUND,
        **conflict("The username is already taken by another user."),
        **INTERNAL,
    },
)
def update_user(db: Db, user_id: OwnUserId, body: schemas.UpdateUserBody):
    return accounts.update_profile(db, user_id, body)


@router.delete(
    "/{id}",
    operation_id="deleteUser",
    summary="Delete your own account",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_description="Deleted. All of your sessions are revoked.",
    responses={**UNAUTHORIZED, **NOT_FOUND, **INTERNAL},
)
def delete_user(db: Db, user_id: OwnUserId) -> None:
    accounts.delete_account(db, user_id)
