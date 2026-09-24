"""The API's request and response bodies. These models validate requests,
filter responses (only declared fields are serialized) and generate the
OpenAPI document. Class names are the OpenAPI component names."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic.json_schema import SkipJsonSchema


def _drop_property_titles(schema: dict[str, Any]) -> None:
    # Pydantic titles every property ("Firstname"); they only add noise to
    # the document and the generated client.
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)


class ApiModel(BaseModel):
    """camelCase in JSON, snake_case in Python. Unknown keys are ignored."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="ignore",
        json_schema_extra=_drop_property_titles,
    )


class ResponseModel(ApiModel):
    # Documents `additionalProperties: false`: responses carry exactly the
    # declared fields.
    model_config = ConfigDict(extra="forbid")


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# A last name may be empty: not everyone has one.
LastName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=30,
        pattern=r"^[a-zA-Z0-9_.]+$",
    ),
    Field(description="3-30 letters, digits, `_` or `.`. Case-insensitive; stored lowercased."),
]
CurrentPassword = Annotated[str, Field(min_length=1, max_length=128)]
NewPassword = Annotated[str, Field(min_length=8, max_length=128)]
# Deliberately not `Username`: a malformed login name fails like an unknown
# one (401), not with a telling 400.
LoginName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    USERNAME_TAKEN = "USERNAME_TAKEN"
    INVALID_PASSWORD = "INVALID_PASSWORD"
    INTERNAL = "INTERNAL"


class ValidationIssue(ResponseModel):
    path: list[str | int]
    code: str
    message: str


class ErrorBody(ResponseModel):
    code: ErrorCode
    message: str
    details: list[ValidationIssue] | SkipJsonSchema[None] = None


class Error(ResponseModel):
    error: ErrorBody


class Health(ResponseModel):
    status: Literal["ok"]


class User(ResponseModel):
    """A user. Never includes credentials."""

    id: uuid.UUID
    username: str
    first_name: str
    last_name: str
    created_at: datetime
    updated_at: datetime


class LoginResponse(ResponseModel):
    token: str = Field(description="Send as `Authorization: Bearer <token>`.")
    user: User


class ChangePasswordResponse(ResponseModel):
    token: str = Field(description="The new bearer token. Every previous token is revoked.")


# ---------------------------------------------------------------------------
# Requests
#
# Optional fields are typed without `| None` and default to None: defaults
# aren't validated, so an omitted field is None while an explicit `null` is a
# validation error, and the OpenAPI schema says "string, not required".
# ---------------------------------------------------------------------------


# Without names, `firstName` is the username and `lastName` is empty.
class RegisterBody(ApiModel):
    username: Username
    password: NewPassword
    first_name: Name = None
    last_name: LastName = None


class LoginBody(ApiModel):
    username: LoginName = Field(description="Case-insensitive.")
    password: CurrentPassword


class UpdateUserBody(ApiModel):
    username: Username = None
    first_name: Name = None
    last_name: LastName = None

    @model_validator(mode="after")
    def at_least_one(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one of username, firstName or lastName")
        return self


class ChangePasswordBody(ApiModel):
    current_password: CurrentPassword
    new_password: NewPassword
