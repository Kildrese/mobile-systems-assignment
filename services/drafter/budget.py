"""One page by line budget, not by rendering (design D4).

`lines(doc)` adds up the body: 1 line for each non-bullet paragraph and spacer, and
ceil(len / 105) for a bullet; a table row counts its tallest cell. The budget is the
master's own count plus one line of margin inside the ~3 free lines Word leaves.
Over budget, `checks.yaml`'s cut order applies one step at a time.
"""

import math
from collections.abc import Callable

from agentkit.contract import CheckRecord
from agentkit.cv.layout import Bullet, Master, Plan, is_bullet, text_of
from agentkit.cv.profile import Checks, CutStep, Fact
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn

from checks import words

BULLET_CHARS = 105
MARGIN_LINES = 1
# A wrapping bullet may give way to an item that shares this share of its words.
VARIANT_OVERLAP = 0.5


def _p_lines(p) -> int:
    return max(1, math.ceil(len(text_of(p)) / BULLET_CHARS)) if is_bullet(p) else 1


def lines(doc: DocxDocument) -> int:
    total = 0
    for el in doc.element.body:
        if el.tag == qn("w:p"):
            total += _p_lines(el)
        elif el.tag == qn("w:tbl"):
            for tr in el.findall(qn("w:tr")):
                total += max(sum(_p_lines(p) for p in tc.findall(qn("w:p"))) for tc in tr.findall(qn("w:tc")))
    return total


def fit(
    master: Master,
    plan: Plan,
    checks: Checks,
    role: str,
    facts: dict[str, Fact],
    record: Callable[[CheckRecord], None],
) -> DocxDocument | None:
    """The built CV once it fits, cutting as needed; None if the whole cut order isn't enough."""
    limit = lines(master.build(master.master_plan())) + MARGIN_LINES
    protected = checks.never_cut | checks.role(role).never_cut
    steps = iter(checks.cut_order)
    while True:
        doc = master.build(plan)
        if (n := lines(doc)) <= limit:
            return doc
        step = next(steps, None)
        if step is None:
            record(
                CheckRecord(
                    name="does_not_fit",
                    outcome="rejected",
                    detail=f"{n} lines after every cut, budget {limit}",
                )
            )
            return None
        for detail in _cut(step, plan, master, facts, checks, protected):
            record(CheckRecord(name=step.action, outcome="cut", detail=detail))


def _cut(
    step: CutStep,
    plan: Plan,
    master: Master,
    facts: dict[str, Fact],
    checks: Checks,
    protected: frozenset[str],
) -> list[str]:
    if step.action == "drop_line":
        if any(t.startswith(step.line) for t in master.fixed_lines) and step.line not in plan.dropped_lines:
            plan.dropped_lines.append(step.line)
            return [step.line]
        return []
    if step.action == "drop_bullets":
        block = plan.subprojects[-1] if step.block == "last_subproject" else step.block
        bullets = plan.bullets.get(block, [])
        out = []
        for b in reversed(list(bullets)):
            if len(bullets) <= step.keep:
                break
            if not protected & set(b.fact_ids):
                bullets.remove(b)
                out.append(f"{block}: {', '.join(b.fact_ids) or b.text[:40]}")
        return out
    # shorten_wrapping: a wrapping bullet gives way to the shortest one-line item about the
    # same thing: its own source text, or an unused approved item in the block that shares
    # half its words.
    # ponytail: word overlap stands in for "same fact"; add a variant_of key to the fact
    # bank if it picks the wrong item.
    used = {i for bs in plan.bullets.values() for b in bs for i in b.fact_ids}
    out = []
    for block, bullets in plan.bullets.items():
        for n, b in enumerate(bullets):
            if len(b.text) <= BULLET_CHARS or protected & set(b.fact_ids):
                continue
            src = words(b.text)
            options = [
                f
                for f in facts.values()
                if len(f.text) <= BULLET_CHARS
                and f.approved
                and f.id not in checks.never_on_cv
                and master.block_of(f) == block
                and (f.id in b.fact_ids or f.id not in used)
                and len(src & words(f.text)) / max(1, len(words(f.text))) >= VARIANT_OVERLAP
            ]
            if options:
                best = min(options, key=lambda f: len(f.text))
                bullets[n] = Bullet((best.id,), best.text)
                used.add(best.id)
                out.append(f"{block}: {', '.join(b.fact_ids)} -> {best.id}")
    return out
