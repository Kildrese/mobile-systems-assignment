from fastapi import APIRouter, Response, status

from app import schemas
from app.deps import CurrentSession, CurrentUser, Db
from app.routers.responses import (
    BAD_REQUEST,
    FORBIDDEN,
    INTERNAL,
    UNAUTHORIZED,
    conflict,
    unauthenticated,
)
from app.services import accounts

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post(
    "/register",
    operation_id="register",
    summary="Create an account",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.User,
    response_description="The created user. No token; log in next.",
    responses={
        **BAD_REQUEST,
        **conflict("The username is already taken."),
        **INTERNAL,
    },
)
def register(db: Db, body: schemas.RegisterBody):
    return accounts.register(db, body)


@router.post(
    "/login",
    operation_id="login",
    summary="Log in and get a bearer token",
    response_model=schemas.LoginResponse,
    response_description="A bearer token and the user.",
    responses={
        **BAD_REQUEST,
        **unauthenticated("Unknown username or wrong password (indistinguishable)."),
        **INTERNAL,
    },
)
def login(db: Db, body: schemas.LoginBody):
    token, user = accounts.login(db, body)
    return {"token": token, "user": user}


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Get the logged-in user",
    response_model=schemas.User,
    response_description="The logged-in user.",
    responses={**UNAUTHORIZED, **INTERNAL},
)
def get_current_user(user: CurrentUser):
    return user


@router.post(
    "/logout",
    operation_id="logout",
    summary="Log out (revoke the current token)",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_description="The token is revoked. Your other sessions stay valid.",
    responses={**UNAUTHORIZED, **INTERNAL},
)
def logout(db: Db, session: CurrentSession) -> None:
    accounts.logout(db, session)


@router.post(
    "/change-password",
    operation_id="changePassword",
    summary="Change your password",
    response_model=schemas.ChangePasswordResponse,
    response_description=(
        "Every session is revoked, including this one. Use the returned token from now on."
    ),
    responses={**BAD_REQUEST, **UNAUTHORIZED, **FORBIDDEN, **INTERNAL},
)
def change_password(db: Db, session: CurrentSession, body: schemas.ChangePasswordBody):
    return {"token": accounts.change_password(db, session.user_id, body)}
