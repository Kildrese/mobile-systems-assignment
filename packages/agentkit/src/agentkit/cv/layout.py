"""The layout map of the master CV: find its parts, and build a tailored copy from a plan.

Written for one layout (the applicant's master, described in `cv_structure.md`):
- four bold headings, EDUCATION, EXPERIENCE, PROJECTS and ADDITIONAL INFORMATION, each with
  a spacer paragraph before and after it;
- an experience table whose entries start with a row of two cells, a bold organization on
  the left and the place and dates on the right;
- inside one entry, several sub-projects, each a plain line ("Name, descriptor (tech)")
  followed by bullets; elsewhere at most one line per entry or project;
- bullets as `List Paragraph` paragraphs with a numbering id;
- a skills table of lines that start with a bold label ("Languages & Frameworks: ...").

Code builds a CV only by cloning a sibling bullet and replacing its text, moving whole
rows, sections and sub-project groups, removing paragraphs, and rewriting the item list
of a skills line. It never changes fonts, sizes, spacing, margins, headers, hyperlinks or
any part of the package other than the body. Every build starts again from the master's
bytes, so a plan can be built, measured and changed as often as needed.
"""

import copy
import io
import re
from dataclasses import dataclass, field

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from lxml.etree import _Element

from agentkit.cv.profile import Fact

SECTIONS = ("EDUCATION", "EXPERIENCE", "PROJECTS", "ADDITIONAL INFORMATION")
_W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_NAME_END = re.compile(r",|\s\(")


class LayoutError(ValueError):
    """The file doesn't have the master's layout."""


def text_of(el: _Element) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def is_bullet(p: _Element) -> bool:
    ppr = p.find(qn("w:pPr"))
    return ppr is not None and ppr.find(qn("w:numPr")) is not None


def _starts_bold(p: _Element) -> bool:
    for r in p.iter(qn("w:r")):
        if not "".join(t.text or "" for t in r.findall(qn("w:t"))).strip():
            continue
        rpr = r.find(qn("w:rPr"))
        b = rpr.find(qn("w:b")) if rpr is not None else None
        return b is not None and b.get(qn("w:val"), "1") not in ("0", "false")
    return False


def _bold_prefix(p: _Element) -> str:
    """The text of the leading bold runs."""
    out = []
    for r in p.iter(qn("w:r")):
        t = "".join(x.text or "" for x in r.findall(qn("w:t")))
        if not t:
            continue
        rpr = r.find(qn("w:rPr"))
        if rpr is None or rpr.find(qn("w:b")) is None:
            break
        out.append(t)
    return "".join(out)


def _short_name(line: str) -> str:
    return _NAME_END.split(line, maxsplit=1)[0].strip()


def _cell_paras(tr: _Element, cell: int = 0) -> list[_Element]:
    tcs = tr.findall(qn("w:tc"))
    return tcs[cell].findall(qn("w:p")) if len(tcs) > cell else []


def _remove(el: _Element) -> None:
    """Remove a paragraph; a table cell left without one takes its row with it."""
    parent = el.getparent()
    parent.remove(el)
    if parent.tag == qn("w:tc") and parent.find(qn("w:p")) is None:
        tr = parent.getparent()
        tr.getparent().remove(tr)


def _set_text(t: _Element, text: str) -> None:
    t.text = text
    if text != text.strip():
        t.set(_XML_SPACE, "preserve")


def clone_bullet(template: _Element, text: str) -> _Element:
    """A copy of a bullet paragraph with only its text replaced."""
    p = copy.deepcopy(template)
    for attr in [a for a in p.attrib if a.startswith(_W14)]:  # paragraph ids must stay unique
        del p.attrib[attr]
    keep = next(r for r in p.findall(qn("w:r")) if r.find(qn("w:t")) is not None)
    for child in list(p):
        if child.tag != qn("w:pPr") and child is not keep:
            p.remove(child)
    ts = keep.findall(qn("w:t"))
    for t in ts[1:]:
        keep.remove(t)
    _set_text(ts[0], text)
    return p


@dataclass(frozen=True)
class Block:
    """A place that holds variable bullets: an entry, an ipt-style sub-project or a project."""

    name: str
    org: str  # what fact-bank entries for it start with
    section: str  # "experience" or "projects"
    subproject: bool
    bullets: tuple[str, ...]  # the master's bullet texts


@dataclass(frozen=True)
class Bullet:
    fact_ids: tuple[str, ...]
    text: str


@dataclass
class Plan:
    bullets: dict[str, list[Bullet]]  # block name -> bullets, in order
    subprojects: list[str]  # sub-project order
    skills: dict[str, list[str]]  # skills label -> items, in order
    projects_under_education: bool = False
    dropped_lines: list[str] = field(default_factory=list)  # fixed lines removed by cuts


@dataclass
class _Parts:
    sections: dict[str, list[_Element]]
    blocks: list[Block]
    bullet_els: dict[str, list[_Element]]
    # The sub-project entry: its line paragraphs by name, the rows they span, a spacer.
    sub_lines: dict[str, _Element]
    sub_rows: list[_Element]
    sub_spacer: _Element | None
    fixed_lines: list[_Element]  # bullets of the education table and skills lines
    skills: dict[str, _Element]
    other_lines: set[str]  # texts of non-bullet lines (entry and product lines)


def _locate(doc: DocxDocument) -> _Parts:
    body = doc.element.body
    children = list(body)
    heads = {
        text_of(el).strip(): i
        for i, el in enumerate(children)
        if el.tag == qn("w:p") and text_of(el).strip() in SECTIONS
    }
    if missing := [s for s in SECTIONS if s not in heads]:
        raise LayoutError(f"no {missing[0]} heading")
    order = sorted(heads.values())
    last = max(i for i, el in enumerate(children) if el.tag == qn("w:tbl") or text_of(el).strip())
    sections = {}
    for n, h in enumerate(order):
        end = order[n + 1] - 1 if n + 1 < len(order) else last + 1
        sections[text_of(children[h]).strip()] = children[h - 1 : end]

    def first_table(section: str) -> _Element:
        tbl = next((el for el in sections[section] if el.tag == qn("w:tbl")), None)
        if tbl is None:
            raise LayoutError(f"no table under {section}")
        return tbl

    blocks: list[Block] = []
    bullet_els: dict[str, list[_Element]] = {}
    other_lines: set[str] = set()
    sub_lines: dict[str, _Element] = {}
    sub_rows: list[_Element] = []
    sub_spacer = None

    def add(name: str, org: str, section: str, sub: bool, els: list[_Element]) -> None:
        if name in bullet_els:
            raise LayoutError(f"two blocks are named '{name}'")
        blocks.append(Block(name, org, section, sub, tuple(text_of(p) for p in els)))
        bullet_els[name] = els

    rows = first_table("EXPERIENCE").findall(qn("w:tr"))
    heads_at = [
        i
        for i, tr in enumerate(rows)
        if len(tr.findall(qn("w:tc"))) >= 2
        and _cell_paras(tr)
        and _starts_bold(_cell_paras(tr)[0])
        and text_of(tr.findall(qn("w:tc"))[-1]).strip()
    ]
    if not heads_at:
        raise LayoutError("the experience table has no entries")
    for n, h in enumerate(heads_at):
        org = _bold_prefix(_cell_paras(rows[h])[0]).strip().rstrip(",").strip()
        entry_rows = rows[h + 1 : heads_at[n + 1] if n + 1 < len(heads_at) else len(rows)]
        paras = [(tr, p) for tr in entry_rows for p in _cell_paras(tr)]
        lines = [(tr, p) for tr, p in paras if text_of(p).strip() and not is_bullet(p)]
        if len(lines) < 2:
            other_lines.update(text_of(p).strip() for _, p in lines)
            add(org, org, "experience", False, [p for _, p in paras if is_bullet(p)])
            continue
        if sub_lines:
            raise LayoutError("more than one entry has sub-projects")
        current = None
        for _, p in paras:
            if is_bullet(p) and current:
                bullet_els[current].append(p)
            elif text_of(p).strip():
                current = _short_name(text_of(p))
                sub_lines[current] = p
                add(current, org, "experience", True, [])
            elif current and sub_spacer is None:
                sub_spacer = p
        blocks[:] = [
            Block(
                b.name,
                b.org,
                b.section,
                b.subproject,
                tuple(text_of(p) for p in bullet_els[b.name]),
            )
            if b.subproject
            else b
            for b in blocks
        ]
        first = entry_rows.index(lines[0][0])
        last_row = max(
            i for i, tr in enumerate(entry_rows) if any(is_bullet(p) for p in _cell_paras(tr))
        )
        sub_rows = entry_rows[first : last_row + 1]
        if any(len(tr.findall(qn("w:tc"))) != 1 for tr in sub_rows):
            raise LayoutError(f"the sub-projects of {org} are not in full-width rows")

    project_paras = [el for el in sections["PROJECTS"][3:] if el.tag == qn("w:p")]
    current = None
    for p in project_paras:
        if is_bullet(p) and current:
            bullet_els[current].append(p)
        elif text_of(p).strip():
            other_lines.add(text_of(p).strip())
            current = _short_name(text_of(p))
            add(current, current, "projects", False, [])
    blocks[:] = [
        Block(b.name, b.org, b.section, b.subproject, tuple(text_of(p) for p in bullet_els[b.name]))
        if b.section == "projects"
        else b
        for b in blocks
    ]

    edu_bullets = [p for p in first_table("EDUCATION").iter(qn("w:p")) if is_bullet(p)]
    skills = {
        text_of(p).split(":", 1)[0].strip(): p
        for p in first_table("ADDITIONAL INFORMATION").iter(qn("w:p"))
        if _starts_bold(p) and ":" in text_of(p)
    }
    if not skills:
        raise LayoutError("no skills lines under ADDITIONAL INFORMATION")
    for b in blocks:
        if not b.bullets:
            raise LayoutError(f"'{b.name}' has no bullet to copy")
    return _Parts(
        sections=sections,
        blocks=blocks,
        bullet_els=bullet_els,
        sub_lines=sub_lines,
        sub_rows=sub_rows,
        sub_spacer=sub_spacer,
        fixed_lines=edu_bullets + list(skills.values()),
        skills=skills,
        other_lines=other_lines,
    )


def _items(p: _Element) -> list[str]:
    return [i.strip() for i in text_of(p).split(":", 1)[1].split(",") if i.strip()]


def _rewrite_skills(p: _Element, items: list[str]) -> None:
    """Replace the list after the bold label, keeping every run's formatting."""
    runs = [r for r in p.iter(qn("w:r")) if r.find(qn("w:t")) is not None]
    plain = [
        r
        for r in runs
        if r.find(qn("w:rPr")) is None or r.find(qn("w:rPr")).find(qn("w:b")) is None
    ]
    if not plain:
        return
    first = plain[0].find(qn("w:t"))
    prefix = re.match(r"[:\s]*", "".join(text_of(r) for r in plain)).group()
    _set_text(first, prefix + ", ".join(items))
    for r in plain:
        for t in r.findall(qn("w:t")):
            if t is not first:
                r.remove(t)


def _open(data: bytes) -> DocxDocument:
    try:
        return Document(io.BytesIO(data))
    except Exception as err:  # python-docx raises several types for a non-docx file
        raise LayoutError(f"not a valid .docx file ({type(err).__name__})") from None


class Master:
    """A parsed master CV. Raises `LayoutError` if the file doesn't have its layout."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        doc = _open(data)
        parts = _locate(doc)
        self.blocks = {b.name: b for b in parts.blocks}
        self.subprojects = list(parts.sub_lines)
        self.skills = {label: _items(p) for label, p in parts.skills.items()}
        self.fixed_lines = [text_of(p).strip() for p in parts.fixed_lines]
        self._other_lines = parts.other_lines
        body = [el for el in doc.element.body if el.tag == qn("w:p")]
        self.name = text_of(body[0]).strip()
        # The contact line up to its first line break: city, phone and email.
        first_line = []
        for el in body[1].iter(qn("w:t"), qn("w:br")):
            if el.tag == qn("w:br"):
                break
            first_line.append(el.text or "")
        self.contact = "".join(first_line).strip().rstrip("|").strip()

    def block_of(self, fact: Fact) -> str | None:
        """The block a fact's bullet belongs under, or None (a heading line, or no block)."""
        if fact.text.strip() in self._other_lines:
            return None
        matches = [
            b
            for b in self.blocks.values()
            if b.section == fact.section
            and fact.entry.startswith(b.org + ":")
            and (not b.subproject or b.name in fact.entry)
        ]
        # The longest name wins, so "Search" never takes the facts of "Search Ranking".
        return max(matches, key=lambda b: len(b.name)).name if matches else None

    def subproject_order(self, order: list[str]) -> list[str]:
        """The order sub-projects render in: `order`'s known names, then the rest as in
        the master."""
        names = [n for n in order if n in self.subprojects]
        return names + [n for n in self.subprojects if n not in names]

    def master_plan(self) -> Plan:
        return Plan(
            bullets={n: [Bullet((), t) for t in b.bullets] for n, b in self.blocks.items()},
            subprojects=list(self.subprojects),
            skills={k: list(v) for k, v in self.skills.items()},
        )

    def build(self, plan: Plan) -> DocxDocument:
        doc = _open(self.data)
        parts = _locate(doc)
        if plan.projects_under_education:  # first, while the section lists are current
            anchor = parts.sections["EDUCATION"][-1]
            for el in reversed(parts.sections["PROJECTS"]):
                anchor.addnext(el)
        for name, els in parts.bullet_els.items():
            texts = [
                b.text
                for b in plan.bullets.get(name, [Bullet((), t) for t in self.blocks[name].bullets])
            ]
            for text in texts:
                els[0].addprevious(clone_bullet(els[0], text))
            for p in els:
                p.getparent().remove(p)  # a row left empty is rebuilt or removed below

        if parts.sub_rows:
            self._regroup(parts, plan.subprojects)
        for tr in list(doc.element.body.iter(qn("w:tr"))):
            if any(tc.find(qn("w:p")) is None for tc in tr.findall(qn("w:tc"))):
                tr.getparent().remove(tr)

        for prefix in plan.dropped_lines:
            for p in parts.fixed_lines:
                if p.getparent() is not None and text_of(p).strip().startswith(prefix):
                    _remove(p)
        for label, items in plan.skills.items():
            if label in parts.skills and parts.skills[label].getparent() is not None:
                _rewrite_skills(parts.skills[label], items)
        return doc

    def _regroup(self, parts: _Parts, order: list[str]) -> None:
        """Rebuild the sub-project rows: per sub-project one row for its line and one for its
        bullets, a spacer row between sub-projects, in the plan's order."""
        names = self.subproject_order(order)
        template = parts.sub_rows[0]
        # The bullets now sit right after their line, wherever the master put them.
        groups = {}
        for name, line in parts.sub_lines.items():
            bullets, nxt = [], line.getnext()
            while nxt is not None and nxt.tag == qn("w:p") and is_bullet(nxt):
                bullets.append(nxt)
                nxt = nxt.getnext()
            if line.getnext() is None:  # the line ends its cell; the bullets start the next row
                row = line.getparent().getparent().getnext()
                bullets = [p for p in _cell_paras(row) if is_bullet(p)] if row is not None else []
            groups[name] = (line, bullets)

        def row(paras: list[_Element]) -> _Element:
            tr = copy.deepcopy(template)
            tc = tr.find(qn("w:tc"))
            for child in list(tc):
                if child.tag != qn("w:tcPr"):
                    tc.remove(child)
            tc.extend(paras)
            return tr

        new_rows = []
        for n, name in enumerate(names):
            if n and parts.sub_spacer is not None:
                new_rows.append(row([copy.deepcopy(parts.sub_spacer)]))
            line, bullets = groups[name]
            new_rows.append(row([line]))
            if bullets:
                new_rows.append(row(bullets))
        for tr in new_rows:
            template.addprevious(tr)
        for tr in parts.sub_rows:
            if tr.getparent() is not None:
                tr.getparent().remove(tr)

    def build_bytes(self, plan: Plan) -> bytes:
        buf = io.BytesIO()
        self.build(plan).save(buf)
        return buf.getvalue()


def paragraph_texts(doc: DocxDocument) -> list[str]:
    """Every paragraph's text in body order, tables included."""
    return [text_of(p) for p in doc.element.body.iter(qn("w:p"))]
