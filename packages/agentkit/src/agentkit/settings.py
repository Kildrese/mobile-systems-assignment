"""Fetch policy: which URLs may be fetched, and how long and how much."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

SAFE_SCHEMES = {"http", "https"}


def host_patterns(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        raise ValueError("at least one host pattern is required (use '*' for any)")
    for pattern in value:
        bare = pattern.removeprefix("*.")
        if pattern != "*" and (not bare or "*" in bare or "/" in bare):
            raise ValueError(f"'{pattern}' is not an exact host, '*.domain' or '*'")
    return tuple(p.lower().rstrip(".") for p in value)


class FetchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_schemes: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    connect_timeout: float = Field(gt=0)
    read_timeout: float = Field(gt=0)
    deadline_seconds: float = Field(gt=0)
    max_bytes: int = Field(gt=0)
    max_redirects: int = Field(default=5, ge=0, le=20)
    max_chars_for_model: int = Field(gt=0)

    @field_validator("allowed_schemes")
    @classmethod
    def only_http(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        value = tuple(s.lower() for s in value)
        if not value:
            raise ValueError("at least one scheme is required")
        if unsafe := [s for s in value if s not in SAFE_SCHEMES]:
            raise ValueError(f"only http and https may be allowed, got {', '.join(unsafe)}")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def host_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return host_patterns(value)
