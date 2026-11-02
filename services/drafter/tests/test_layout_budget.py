import io
import zipfile
from dataclasses import replace

import pytest
from agentkit.cv.layout import Block, Bullet, LayoutError, Master, paragraph_texts
from agentkit.cv.profile import Fact
from docx import Document
from docx.oxml.ns import qn

from budget import BULLET_CHARS, _cut, fit, lines

MASTER_LINES = 62  # re-measure in Word if the master changes, then update this


def _zip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def _c14n(xml: bytes) -> bytes:
    from lxml import etree

    return etree.tostring(etree.fromstring(xml), method="c14n")


def _formats(doc) -> list[str]:
    """Every run's and paragraph's formatting, as XML, in order."""
    out = []
    for tag in ("w:rPr", "w:pPr", "w:sectPr"):
        out += sorted(Document_xml(el) for el in doc.element.body.iter(qn(tag)))
    # Splitting the irregular sub-project row copies its cell, so compare distinct cells.
    for tag in ("w:tblPr", "w:tcPr", "w:trPr"):
        out += sorted({Document_xml(el) for el in doc.element.body.iter(qn(tag))})
    return out


def Document_xml(el) -> str:
    from lxml import etree

    return etree.tostring(el).decode()


# 3.2 the layout map


@pytest.mark.parametrize("which", ["profile", "real_profile"])
def test_rebuilding_the_master_changes_nothing(which, request):
    p = request.getfixturevalue(which)
    original = Document(io.BytesIO(p.cv))
    built_bytes = p.master.build_bytes(p.master.master_plan())
    built = Document(io.BytesIO(built_bytes))
    assert paragraph_texts(built) == paragraph_texts(original)
    assert _formats(built) == _formats(original)
    before, after = _zip(p.cv), _zip(built_bytes)
    assert before.keys() == after.keys()
    for name in before:
        if name.startswith("customXml/") or name.endswith(("styles.xml", "numbering.xml", "settings.xml")):
            assert _c14n(before[name]) == _c14n(after[name]), name
    rels = lambda d: sorted(r._target for r in d.part.rels.values() if r.is_external)  # noqa: E731
    assert rels(built) == rels(original)


def test_blocks_found(profile):
    m = profile.master
    assert m.subprojects == [
        "Claims Portal",
        "Document Parsing Pipeline",
        "Permit Tracking Application",
        "Event Integration Hub",
    ]
    assert list(m.blocks)[4:] == ["cardly", "medrelay", "Stridewell", "Contract Review Assistant"]
    assert m.skills["AI, Data & Cloud"][-1] == "CI/CD"
    assert m.contact == "Springfield, ST | +1 (555) 010-0100 | sam@example.com"


def test_cloned_bullets_keep_the_master_formatting(profile):
    m = profile.master
    plan = m.master_plan()
    plan.bullets["cardly"] = [
        Bullet(("x",), "Built a new thing"),
        *plan.bullets["cardly"],
        Bullet(("y",), "And one more"),
    ]
    plan.subprojects = list(reversed(plan.subprojects))
    doc = m.build(plan)
    bullets = [
        p
        for p in doc.element.body.iter(qn("w:p"))
        if p.find(qn("w:pPr")) is not None and p.find(qn("w:pPr")).find(qn("w:numPr")) is not None
    ]
    template = next(
        p
        for p in Document(io.BytesIO(profile.cv)).element.body.iter(qn("w:p"))
        if "1,200+ events" in "".join(t.text or "" for t in p.iter(qn("w:t")))
    )
    new = next(p for p in bullets if "Built a new thing" in "".join(t.text for t in p.iter(qn("w:t"))))
    assert Document_xml(new.find(qn("w:pPr"))) == Document_xml(template.find(qn("w:pPr")))
    texts = paragraph_texts(doc)
    assert texts.index("Built a new thing") < texts.index("And one more")
    # Sub-projects moved as whole groups.
    assert texts.index("Event Integration Hub (MuleSoft, Kafka, Azure, Java)") < texts.index(
        "Claims Portal, Regional Insurer (Angular, Java Quarkus, Salesforce, MongoDB, Kafka)"
    )
    assert texts.index(
        "Helped move the message bus to Azure and set code standards for the integration team"
    ) < texts.index("Permit Tracking Application (Angular, Spring Boot, PostgreSQL)")


def test_projects_under_education_and_dropped_lines(profile):
    m = profile.master
    plan = m.master_plan()
    plan.projects_under_education = True
    plan.dropped_lines = ["Interests", "Research paper", "Thesis"]
    plan.bullets["Stridewell"] = []
    texts = paragraph_texts(m.build(plan))
    assert texts.index("PROJECTS") < texts.index("EXPERIENCE")
    assert (
        texts.count(
            "Building a multi-agent system that reads several contract sources to support review decisions"
        )
        == 1
    )
    assert not any(t.startswith(("Interests", "Thesis", "Research paper")) for t in texts)
    assert not any("running cadence" in t for t in texts)


def test_skills_rewritten_in_place(profile):
    m = profile.master
    plan = m.master_plan()
    plan.skills["Languages & Frameworks"] = list(reversed(m.skills["Languages & Frameworks"]))
    texts = paragraph_texts(m.build(plan))
    assert (
        "Languages & Frameworks: Swift, FastAPI, Quarkus, Spring Boot, Node.js, Angular, React, Java, "
        "Python, TypeScript" in texts
    )


def test_unknown_layout_rejected(profile):
    doc = Document(io.BytesIO(profile.cv))
    for t in doc.element.body.iter(qn("w:t")):
        if t.text == "EXPERIENCE":
            t.text = "WORK"
    buf = io.BytesIO()
    doc.save(buf)
    with pytest.raises(LayoutError, match="EXPERIENCE"):
        Master(buf.getvalue())
    with pytest.raises(LayoutError, match=r"not a valid \.docx"):
        Master(b"not a docx")


# 3.3 the line budget and the cut order


def test_master_fits(profile, real_profile):
    for p in (profile, real_profile):
        assert lines(p.master.build(p.master.master_plan())) == MASTER_LINES
    cuts = []
    doc = fit(profile.master, profile.master.master_plan(), profile.checks, "swe", profile.facts, cuts.append)
    assert doc is not None and cuts == []


def test_two_long_bullets_are_cut_by_the_cut_order(profile):
    m = profile.master
    plan = m.master_plan()

    def long(fid):
        return profile.facts[fid].text + ", working closely with the wider team on every release"

    plan.bullets["Claims Portal"][:2] = [
        Bullet(("exp.nws.1",), long("exp.nws.1")),
        Bullet(("exp.nws.2",), long("exp.nws.2")),
    ]
    plan.bullets["cardly"].append(Bullet(("exp.cardly.4",), long("exp.cardly.4")))
    assert all(BULLET_CHARS < len(b.text) <= 2 * BULLET_CHARS for b in plan.bullets["Claims Portal"][:2])
    cuts = []
    doc = fit(m, plan, profile.checks, "swe", profile.facts, cuts.append)
    assert doc is not None and lines(doc) <= MASTER_LINES + 1
    assert cuts and all(c.outcome == "cut" for c in cuts)
    assert cuts[0].name == "shorten_wrapping"


def test_never_cut_ids_survive(profile):
    m = profile.master
    plan = m.master_plan()
    plan.bullets["cardly"] = [
        Bullet(("exp.cardly.1",), profile.facts["exp.cardly.1"].text),
        Bullet(("exp.cardly.2",), profile.facts["exp.cardly.2"].text),
    ]
    plan.bullets["medrelay"] = [Bullet(("exp.medrelay.1",), profile.facts["exp.medrelay.1"].text)]
    for block in m.subprojects:
        plan.bullets[block] = [Bullet(("z",), "Wrote " + "long words " * 18) for _ in range(3)]
    extra = replace(profile.checks.cut_order[-1], block="cardly", keep=0)
    checks = replace(profile.checks, cut_order=(*profile.checks.cut_order, extra))
    cuts = []
    doc = fit(m, plan, checks, "swe", profile.facts, cuts.append)
    texts = paragraph_texts(doc) if doc is not None else []
    assert all("exp.cardly.1" not in c.detail for c in cuts)
    if doc is not None:
        assert profile.facts["exp.cardly.1"].text in texts


def test_last_subproject_cut_uses_the_rendered_order(profile):
    m = profile.master
    step = next(s for s in profile.checks.cut_order if s.block == "last_subproject")
    plan = m.master_plan()
    plan.subprojects = []  # a role row without sub-projects: the master's order renders
    _cut(step, plan, m, profile.facts, profile.checks, frozenset())
    assert len(plan.bullets["Event Integration Hub"]) == 1
    plan = m.master_plan()
    plan.subprojects = ["Event Integration Hub", "Claims Portal"]  # the rest follow, in master order
    _cut(step, plan, m, profile.facts, profile.checks, frozenset())
    assert len(plan.bullets["Permit Tracking Application"]) == 1
    assert len(plan.bullets["Claims Portal"]) == 3


def test_longest_block_name_wins(profile):
    m = Master(profile.cv)
    m.blocks = {
        "Search": Block("Search", "Org", "experience", True, ("b",)),
        "Search Ranking": Block("Search Ranking", "Org", "experience", True, ("b",)),
    }
    fact = Fact("x", "experience", "Org: Consultant, Search Ranking (2024)", "Built it", (), False, True)
    assert m.block_of(fact) == "Search Ranking"


def test_does_not_fit(profile):
    m = profile.master
    plan = m.master_plan()
    for block in m.blocks:
        plan.bullets[block] = [Bullet(("exp.medrelay.1",), "Built " + "x" * 300)] * 3
    cuts = []
    assert fit(m, plan, profile.checks, "swe", profile.facts, cuts.append) is None
    assert cuts[-1].name == "does_not_fit"
