"""Code checks on the model's plan and letter (design D6, D7). The model proposes; this decides.

A bullet is kept only when its fact ids name approved items allowed on a CV and placed
under the block it's in. A rewording is kept only when it keeps the source's facts, stays
close to its words and length, and adds no scope word, banned word or em dash; otherwise
the source text is used. Every change is recorded for the applicant.
"""

import re
from collections.abc import Callable

from agentkit.contract import CheckRecord
from agentkit.cv.layout import Bullet, Master, Plan
from agentkit.cv.profile import Checks, Fact
from pydantic import BaseModel, Field

# Tuned against examples.md's real rewordings: stricter means blander, never wrong.
MIN_SHARED = 0.6  # of the rewording's words that come from the source
MAX_GROWTH = 1.15  # rewording length over source length
LETTER_WORDS = (300, 420)
LETTER_FORBIDDEN = ("visa", "CPT", "F-1", "sponsorship", "sponsor", "salary")
_MONTHS = "january february march april may june july august september october november december"
ALWAYS_KNOWN = {"i", *_MONTHS.split(), *(m[:3] for m in _MONTHS.split())}
_TOKEN = re.compile(r"[~$€]?[A-Za-z0-9](?:[A-Za-z0-9+#&/.,]*[A-Za-z0-9+#])?")
_SENTENCE = re.compile(r"(?<=[.!?:;])\s+|\n+")


class PlanBullet(BaseModel):
    fact_ids: list[str] = Field(min_length=1, max_length=2)
    text: str = Field(min_length=1, max_length=400)


class PlanBlock(BaseModel):
    block: str
    bullets: list[PlanBullet] = Field(max_length=6)


class PlanSkills(BaseModel):
    label: str
    items: list[str] = Field(max_length=20)


class ModelPlan(BaseModel):
    """What the model returns for the CV."""

    role_type: str = Field(max_length=50)
    blocks: list[PlanBlock] = Field(max_length=20)
    skills: list[PlanSkills] = Field(default_factory=list, max_length=6)


class ModelLetter(BaseModel):
    paragraphs: list[str] = Field(min_length=1, max_length=8)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def words(text: str) -> set[str]:
    return {t.lower() for t in tokens(text)}


def names(text: str) -> set[str]:
    """Numbers, dates and capitalized names, without the capital that starts a sentence."""
    out = set()
    for sentence in _SENTENCE.split(text):
        for n, t in enumerate(tokens(sentence)):
            if any(c.isdigit() for c in t) or (t[0].isupper() and not (n == 0 and t.isalpha())):
                out.add(t.lower())
    return out


def has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text, re.IGNORECASE) is not None


def reword_problem(source: str, text: str, checks: Checks) -> tuple[str, str] | None:
    """Why a rewording can't replace its source, or None if it can."""
    if "—" in text:
        return "em_dash", "an em dash"
    if banned := next((w for w in checks.banned_words if has_phrase(text, w)), None):
        return "banned_word", banned
    scope = next((w for w in checks.scope_words if has_phrase(text, w) and not has_phrase(source, w)), None)
    if scope:
        return "scope_word", scope
    src_words = words(source)
    if lost := sorted(names(source) - words(text)):
        return "fact_changed", f"drops {lost[0]}"
    if added := sorted(names(text) - src_words):
        return "fact_changed", f"adds {added[0]}"
    if len(text) > MAX_GROWTH * len(source):
        return "too_long", f"{len(text)} characters for a source of {len(source)}"
    rew = words(text)
    if rew and len(rew & src_words) / len(rew) < MIN_SHARED:
        return "too_different", f"{len(rew & src_words)} of {len(rew)} words from the source"
    return None


Record = Callable[[CheckRecord], None]


def apply_plan(
    proposed: ModelPlan, master: Master, facts: dict[str, Fact], checks: Checks, record: Record
) -> tuple[Plan, str]:
    """The model's plan, checked against the fact bank, as a plan code can build."""
    role = proposed.role_type
    if role not in checks.role_types:
        record(CheckRecord(name="role_type_unknown", outcome="note", detail=f"{role}: SWE order used"))
    row = checks.role(role)
    order = list(facts)

    by_block = {b.block: b.bullets for b in proposed.blocks}
    for name in by_block:
        if name not in master.blocks:
            record(CheckRecord(name="block_unknown", outcome="dropped", detail=name))

    def allowed(f: Fact) -> bool:
        return f.approved and f.id not in checks.never_on_cv

    used: set[str] = set()
    bullets: dict[str, list[Bullet]] = {}
    for name, block in master.blocks.items():
        kept: list[Bullet] = []
        for b in by_block.get(name, []):
            ids = list(dict.fromkeys(b.fact_ids))
            reason = None
            for i in ids:
                f = facts.get(i)
                reason = (
                    "fact_unknown"
                    if f is None
                    else "fact_unapproved"
                    if not f.approved
                    else "never_on_cv"
                    if i in checks.never_on_cv
                    else "wrong_entry"
                    if master.block_of(f) != name
                    else "fact_repeated"
                    if i in used
                    else None
                )
                if reason:
                    record(CheckRecord(name=reason, outcome="dropped", detail=f"{i} under {name}"))
                    break
            if reason:
                continue
            source = ". ".join(facts[i].text for i in ids)  # each source starts a sentence
            text = " ".join(b.text.split())
            if text != source and (problem := reword_problem(source, text, checks)):
                record(
                    CheckRecord(name=problem[0], outcome="fallback", detail=f"{', '.join(ids)}: {problem[1]}")
                )
                ids, text = ids[:1], facts[ids[0]].text
            kept.append(Bullet(tuple(ids), text))
            used.update(ids)

        low, high = checks.bullet_bounds.get(name, (len(block.bullets), len(block.bullets)))
        if len(kept) > high:
            for b in kept[high:]:
                used.difference_update(b.fact_ids)
                record(CheckRecord(name="over_max", outcome="cut", detail=f"{name}: {', '.join(b.fact_ids)}"))
            kept = kept[:high]
        if len(kept) < low:
            spare = sorted(
                (f for f in facts.values() if allowed(f) and f.id not in used and master.block_of(f) == name),
                key=lambda f: (role not in f.tags, not f.on_master_cv, order.index(f.id)),
            )
            for f in spare[: low - len(kept)]:
                kept.append(Bullet((f.id,), f.text))
                used.add(f.id)
                record(CheckRecord(name="refilled", outcome="refilled", detail=f"{name}: {f.id}"))
        bullets[name] = kept

    skills = {}
    proposed_skills = {s.label: [i.strip() for i in s.items] for s in proposed.skills}
    for label, master_items in master.skills.items():
        items = proposed_skills.get(label, master_items)
        known = set(master_items)
        for f in facts.values():
            if allowed(f) and f.section == "skills" and f.entry.endswith(f": {label}"):
                known.update(i.strip() for i in f.text.split(":", 1)[-1].split(","))
        if items != master_items and (
            len(items) != len(master_items) or len(set(items)) != len(items) or not set(items) <= known
        ):
            unknown = sorted(set(items) - known)
            record(
                CheckRecord(
                    name="skills_rejected",
                    outcome="fallback",
                    detail=f"{label}: "
                    + (
                        f"unknown {', '.join(unknown)}"
                        if unknown
                        else f"needs {len(master_items)} distinct items"
                    ),
                )
            )
            items = master_items
        lead = [i for i in row.skills_lead.get(label, ()) if i in items]
        skills[label] = lead + [i for i in items if i not in lead]

    plan = Plan(
        bullets=bullets,
        subprojects=list(row.subprojects),
        skills=skills,
        projects_under_education=row.projects_under_education,
    )
    return plan, role


def letter_problems(paragraphs: list[str], known_text: str, checks: Checks) -> list[str]:
    """Why a letter can't be used; empty if it can. `known_text` is everything a letter may
    name: the approved facts, the posting, the company and the applicant's header."""
    text = "\n".join(paragraphs)
    problems = []
    count = len(text.split())
    if not LETTER_WORDS[0] <= count <= LETTER_WORDS[1]:
        problems.append(f"{count} words; write {LETTER_WORDS[0]} to {LETTER_WORDS[1]}")
    if "—" in text:
        problems.append("contains an em dash")
    for w in (*LETTER_FORBIDDEN, *checks.client_names):
        if has_phrase(text, w):
            problems.append(f"mentions {w}")
    for w in checks.banned_words:
        if has_phrase(text, w):
            problems.append(f"uses the banned word {w}")
    unknown = sorted(names(text) - words(known_text) - ALWAYS_KNOWN)
    if unknown:
        problems.append(f"names what the fact bank and posting don't: {', '.join(unknown[:5])}")
    return problems
