"""Ranking in code: a deterministic score from config weights.

Each criterion scores 1 for a match, 0 for a mismatch and 0.5 when the record says
`unknown`, so a sparse posting is neither buried nor promoted. Work-authorization
wording is never an input.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tracker.usecases.internships.curation import UNKNOWN, normalize
from tracker.usecases.internships.store import OpportunityStore

LIVE = ("open", "unknown")


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: float = Field(default=3, ge=0)
    term: float = Field(default=3, ge=0)
    location: float = Field(default=2, ge=0)
    recency: float = Field(default=1, ge=0)


class RankingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weights: Weights = Weights()
    recency_days: int = Field(default=30, gt=0)
    role_types: tuple[str, ...] = ("internship",)
    terms: tuple[str, ...] = ("Summer 2027",)
    locations: tuple[str, ...] = ("New York", "NYC", "Brooklyn", "Remote")


def _role(opp: dict[str, Any], s: RankingSettings) -> float:
    if opp["role_type"] == UNKNOWN:
        return 0.5
    return 1.0 if opp["role_type"] in s.role_types else 0.0


def _term(opp: dict[str, Any], s: RankingSettings) -> float:
    if opp["term"] == UNKNOWN:
        return 0.5
    term = normalize(opp["term"])
    return 1.0 if any(normalize(t) in term for t in s.terms) else 0.0


def _location(opp: dict[str, Any], s: RankingSettings) -> float:
    places = [normalize(p) for p in s.locations]
    locations = [normalize(loc) for loc in opp["locations"] if isinstance(loc, str)]
    if opp["remote"] == "remote" and "remote" in places:
        return 1.0
    if not locations:
        return 0.5
    return 1.0 if any(p in loc for loc in locations for p in places) else 0.0


def _recency(opp: dict[str, Any], s: RankingSettings, now: datetime) -> float:
    first_seen = datetime.fromisoformat(opp["first_seen_at"])
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=UTC)
    age_days = max(0.0, (now - first_seen).total_seconds() / 86400)
    return max(0.0, 1.0 - age_days / s.recency_days)


def score(opp: dict[str, Any], settings: RankingSettings, now: datetime) -> float:
    w = settings.weights
    total = (
        w.role * _role(opp, settings)
        + w.term * _term(opp, settings)
        + w.location * _location(opp, settings)
        + w.recency * _recency(opp, settings, now)
    )
    return round(total, 6)


def rank_open(
    store: OpportunityStore,
    run_id: str,
    settings: RankingSettings,
    k: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The Rank stage: score every live opportunity, store ranks, return them in order."""
    now = now or datetime.now(UTC)
    scored = [(score(opp, settings, now), opp) for opp in store.opportunities(LIVE)]
    scored.sort(
        key=lambda pair: (-pair[0], pair[1]["first_seen_at"], pair[1]["company"], pair[1]["id"])
    )
    store.put_ranks(run_id, [(opp["id"], s, i < k) for i, (s, opp) in enumerate(scored)])
    return [{**opp, "rank": i + 1, "score": s, "top_k": i < k} for i, (s, opp) in enumerate(scored)]
