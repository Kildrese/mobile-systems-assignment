"""Parse and validate an applicant's `fact_bank.yaml` and `checks.yaml`.

The backend runs these on upload and the drafter on every request, so a profile that
was accepted once is read the same way everywhere. Errors name the file and the reason.
"""

from dataclasses import dataclass
from typing import Any

import yaml

FACT_KEYS = ("id", "section", "entry", "text", "tags", "on_master_cv", "approved")
CHECK_KEYS = ("banned_words", "scope_words", "cut_order", "role_types", "never_on_cv")
DEFAULT_ROLE = "swe"
CUT_ACTIONS = ("shorten_wrapping", "drop_line", "drop_bullets")


class ProfileError(ValueError):
    def __init__(self, file: str, reason: str) -> None:
        super().__init__(f"{file}: {reason}")
        self.file = file
        self.reason = reason


@dataclass(frozen=True)
class Fact:
    id: str
    section: str
    entry: str
    text: str
    tags: tuple[str, ...]
    on_master_cv: bool
    approved: bool


@dataclass(frozen=True)
class RoleType:
    subprojects: tuple[str, ...]
    skills_lead: dict[str, tuple[str, ...]]
    projects_under_education: bool
    never_cut: frozenset[str]


@dataclass(frozen=True)
class CutStep:
    action: str  # one of CUT_ACTIONS
    line: str = ""  # drop_line: the start of the fixed line to remove
    block: str = ""  # drop_bullets: a block name, or "last_subproject"
    keep: int = 0  # drop_bullets: bullets left in the block


@dataclass(frozen=True)
class Checks:
    banned_words: tuple[str, ...]
    scope_words: tuple[str, ...]
    client_names: tuple[str, ...]
    never_on_cv: frozenset[str]
    never_cut: frozenset[str]
    bullet_bounds: dict[str, tuple[int, int]]
    cut_order: tuple[CutStep, ...]
    role_types: dict[str, RoleType]

    def role(self, name: str) -> RoleType:
        """The role type's row, or the SWE row for a type the table doesn't have."""
        return self.role_types.get(name) or self.role_types[DEFAULT_ROLE]


def _load(file: str, text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise ProfileError(file, f"not valid YAML ({str(err).splitlines()[0]})") from None


def _strings(file: str, key: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileError(file, f"{key} must be a list of strings")
    return tuple(value)


def parse_fact_bank(text: str) -> dict[str, Fact]:
    file = "fact_bank.yaml"
    data = _load(file, text)
    if not isinstance(data, list) or not data:
        raise ProfileError(file, "must be a non-empty list of items")
    facts: dict[str, Fact] = {}
    for n, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ProfileError(file, f"item {n} is not a mapping")
        if missing := [k for k in FACT_KEYS if k not in item]:
            raise ProfileError(
                file, f"item {n} ({item.get('id', 'no id')}) lacks {', '.join(missing)}"
            )
        fid = str(item["id"])
        if fid in facts:
            raise ProfileError(file, f"duplicate id {fid}")
        if not all(isinstance(item[k], str) for k in ("section", "entry", "text")):
            raise ProfileError(file, f"{fid}: section, entry and text must be strings")
        if not isinstance(item["on_master_cv"], bool) or not isinstance(item["approved"], bool):
            raise ProfileError(file, f"{fid}: on_master_cv and approved must be true or false")
        facts[fid] = Fact(
            id=fid,
            section=item["section"],
            entry=item["entry"],
            text=item["text"].strip(),
            tags=_strings(file, f"{fid}: tags", item["tags"]),
            on_master_cv=item["on_master_cv"],
            approved=item["approved"],
        )
    return facts


def _cut_step(file: str, raw: Any) -> CutStep:
    if raw == "shorten_wrapping":
        return CutStep("shorten_wrapping")
    if isinstance(raw, dict) and len(raw) == 1:
        ((action, arg),) = raw.items()
        if action == "drop_line" and isinstance(arg, str) and arg:
            return CutStep("drop_line", line=arg)
        if (
            action == "drop_bullets"
            and isinstance(arg, dict)
            and isinstance(arg.get("block"), str)
            and isinstance(arg.get("keep"), int)
            and arg["keep"] >= 0
        ):
            return CutStep("drop_bullets", block=arg["block"], keep=arg["keep"])
    raise ProfileError(
        file,
        f"cut_order step {raw!r} is not shorten_wrapping, drop_line: <text> or "
        "drop_bullets: {block, keep}",
    )


def parse_checks(text: str, facts: dict[str, Fact]) -> Checks:
    file = "checks.yaml"
    data = _load(file, text)
    if not isinstance(data, dict):
        raise ProfileError(file, "must be a mapping")
    if missing := [k for k in CHECK_KEYS if k not in data]:
        raise ProfileError(file, f"lacks {', '.join(missing)}")

    def ids(key: str, value: Any) -> frozenset[str]:
        found = _strings(file, key, value)
        if unknown := [i for i in found if i not in facts]:
            raise ProfileError(file, f"{key} names ids not in the fact bank: {', '.join(unknown)}")
        return frozenset(found)

    bounds: dict[str, tuple[int, int]] = {}
    for block, b in (data.get("bullet_bounds") or {}).items():
        if not (
            isinstance(b, dict)
            and isinstance(b.get("min"), int)
            and isinstance(b.get("max"), int)
            and 0 <= b["min"] <= b["max"]
        ):
            raise ProfileError(
                file, f"bullet_bounds.{block} must be {{min, max}} with 0 <= min <= max"
            )
        bounds[str(block)] = (b["min"], b["max"])

    roles_raw = data["role_types"]
    if not isinstance(roles_raw, dict) or DEFAULT_ROLE not in roles_raw:
        raise ProfileError(file, f"role_types must be a mapping with a '{DEFAULT_ROLE}' row")
    roles: dict[str, RoleType] = {}
    for name, row in roles_raw.items():
        if not isinstance(row, dict):
            raise ProfileError(file, f"role_types.{name} must be a mapping")
        lead = row.get("skills_lead") or {}
        if not isinstance(lead, dict):
            raise ProfileError(file, f"role_types.{name}.skills_lead must map a label to a list")
        roles[str(name)] = RoleType(
            subprojects=_strings(file, f"role_types.{name}.subprojects", row.get("subprojects")),
            skills_lead={
                str(k): _strings(file, f"role_types.{name}.skills_lead", v) for k, v in lead.items()
            },
            projects_under_education=bool(row.get("projects_under_education", False)),
            never_cut=ids(f"role_types.{name}.never_cut", row.get("never_cut")),
        )

    cut_raw = data["cut_order"]
    if not isinstance(cut_raw, list):
        raise ProfileError(file, "cut_order must be a list")
    return Checks(
        banned_words=_strings(file, "banned_words", data["banned_words"]),
        scope_words=_strings(file, "scope_words", data["scope_words"]),
        client_names=_strings(file, "client_names", data.get("client_names")),
        never_on_cv=ids("never_on_cv", data["never_on_cv"]),
        never_cut=ids("never_cut", data.get("never_cut")),
        bullet_bounds=bounds,
        cut_order=tuple(_cut_step(file, s) for s in cut_raw),
        role_types=roles,
    )
