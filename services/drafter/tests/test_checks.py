import pytest
from agentkit.cv.profile import ProfileError, parse_checks, parse_fact_bank

from checks import ModelPlan, apply_plan, letter_problems, names, reword_problem

SCOPE_SRC = "Helped move the message bus to Azure and set code standards for the integration team"
NUMBER_SRC = "Wrote a Python pipeline on Azure OpenAI that migrated ~400 legacy documents to a new store"


@pytest.mark.parametrize(
    ("source", "text", "problem"),
    [
        # Scope upgrade
        (
            SCOPE_SRC,
            "Led the move of the message bus to Azure and set code standards for the integration team",
            ("scope_word", "led"),
        ),
        # Invented number
        (NUMBER_SRC, NUMBER_SRC.replace("~400", "~500"), ("fact_changed", "drops ~400")),
        # A name the source doesn't have
        (NUMBER_SRC, NUMBER_SRC + " on Kubernetes", ("fact_changed", "adds kubernetes")),
        ("Built the app", "Built the robust app", ("banned_word", "robust")),
        ("Built the app and the API", "Built the app — and the API", ("em_dash", "an em dash")),
        (
            SCOPE_SRC,
            SCOPE_SRC + " and many more people across several offices in town",
            ("too_long", "136 characters for a source of 84"),
        ),
        (
            SCOPE_SRC,
            "Moved bus to Azure; wrote standards people across teams now follow daily",
            ("too_different", "4 of 12 words from the source"),
        ),
    ],
)
def test_rewording_rejected(profile, source, text, problem):
    assert reword_problem(source, text, profile.checks) == problem


def test_good_rewording_kept(profile):
    assert (
        reword_problem(
            SCOPE_SRC,
            "Helped move the message bus to Azure and set the team's code standards",
            profile.checks,
        )
        is None
    )


def _plan(blocks, role="swe", skills=()):
    return ModelPlan.model_validate({"role_type": role, "blocks": blocks, "skills": list(skills)})


def _apply(profile, blocks, **kw):
    records = []
    plan, role = apply_plan(
        _plan(blocks, **kw), profile.master, profile.facts, profile.checks, records.append
    )
    return plan, role, {(r.name, r.outcome) for r in records}, records


def test_scope_upgrade_falls_back_to_source(profile):
    plan, _, seen, records = _apply(
        profile,
        [
            {
                "block": "Event Integration Hub",
                "bullets": [
                    {"fact_ids": ["exp.nws.12"], "text": profile.facts["exp.nws.12"].text},
                    {"fact_ids": ["exp.nws.13"], "text": SCOPE_SRC.replace("Helped move", "Led the move of")},
                ],
            }
        ],
    )
    assert plan.bullets["Event Integration Hub"][1].text == SCOPE_SRC
    assert ("scope_word", "fallback") in seen
    assert any("led" in r.detail for r in records)


def test_unapproved_bullet_dropped_and_refilled(profile):
    plan, _, seen, _ = _apply(
        profile,
        [
            {
                "block": "Permit Tracking Application",
                "bullets": [
                    {"fact_ids": ["exp.nws.8"], "text": profile.facts["exp.nws.8"].text},
                    {"fact_ids": ["exp.nws.10"], "text": profile.facts["exp.nws.10"].text},  # approved: false
                ],
            }
        ],
    )
    ids = [b.fact_ids for b in plan.bullets["Permit Tracking Application"]]
    assert ("exp.nws.10",) not in ids and len(ids) == 2  # the minimum, from another approved item
    assert {("fact_unapproved", "dropped"), ("refilled", "refilled")} <= seen


def test_never_on_cv_dropped(profile):
    plan, _, seen, _ = _apply(
        profile,
        [
            {
                "block": "cardly",
                "bullets": [
                    {"fact_ids": ["exp.cardly.5"], "text": profile.facts["exp.cardly.5"].text},
                ],
            }
        ],
    )
    assert all("exp.cardly.5" not in b.fact_ids for b in plan.bullets["cardly"])
    assert ("never_on_cv", "dropped") in seen


def test_bullet_under_another_entry_dropped(profile):
    plan, _, seen, _ = _apply(
        profile,
        [
            {
                "block": "cardly",
                "bullets": [
                    {"fact_ids": ["exp.medrelay.1"], "text": profile.facts["exp.medrelay.1"].text},
                ],
            }
        ],
    )
    assert ("wrong_entry", "dropped") in seen
    assert all(b.fact_ids[0].startswith("exp.cardly") for b in plan.bullets["cardly"])


def test_merging_two_items_checks_their_union(profile):
    merged = (
        "Built the full-stack claims portal for a regional insurer and connected Salesforce "
        "with Kafka-based claim workflows"
    )
    plan, _, seen, _ = _apply(
        profile,
        [
            {
                "block": "Claims Portal",
                "bullets": [
                    {"fact_ids": ["exp.nws.1", "exp.nws.2"], "text": merged},
                ],
            }
        ],
    )
    assert plan.bullets["Claims Portal"][0].text == merged
    assert plan.bullets["Claims Portal"][0].fact_ids == ("exp.nws.1", "exp.nws.2")
    assert not {name for name, _ in seen} & {"fact_changed", "too_different", "too_long"}


def test_unknown_role_type_uses_swe_order(profile):
    plan, role, seen, _ = _apply(profile, [], role="robotics")
    assert role == "robotics" and ("role_type_unknown", "note") in seen
    assert plan.subprojects == list(profile.checks.role_types["swe"].subprojects)


def test_skills_lead_and_unknown_items(profile):
    items = list(reversed(profile.master.skills["Languages & Frameworks"]))
    plan, _, _, _ = _apply(profile, [], skills=[{"label": "Languages & Frameworks", "items": items}])
    assert plan.skills["Languages & Frameworks"][:4] == ["TypeScript", "Python", "Java", "React"]
    bad = [*profile.master.skills["AI, Data & Cloud"][:-1], "Kubernetes"]
    plan, _, seen, _ = _apply(profile, [], skills=[{"label": "AI, Data & Cloud", "items": bad}])
    assert plan.skills["AI, Data & Cloud"] == profile.master.skills["AI, Data & Cloud"]
    assert ("skills_rejected", "fallback") in seen
    swap = [*profile.master.skills["AI, Data & Cloud"][:-1], "MuleSoft"]  # an approved alternative line
    plan, _, _, _ = _apply(profile, [], skills=[{"label": "AI, Data & Cloud", "items": swap}])
    assert plan.skills["AI, Data & Cloud"] == swap


KNOWN = "Ramp Software Engineer Intern Python Azure OpenAI cardly Northwind Hudson University 2027 ~400"


def _letter(extra=""):
    body = ("I built a Python pipeline on Azure OpenAI at Northwind that moved ~400 documents. " * 25).split()
    return [" ".join(body[:330]) + extra]


@pytest.mark.parametrize(
    ("extra", "problem"),
    [
        (" I am on an F-1 visa.", "mentions visa"),
        (" I will need sponsorship.", "mentions sponsorship"),
        (" I worked for Acme Mutual.", "mentions Acme Mutual"),
        (" It was a robust system.", "uses the banned word robust"),
        (" I — truly — care.", "contains an em dash"),
        (
            " I also used Kubernetes at Google.",
            "names what the fact bank and posting don't: google, kubernetes",
        ),
    ],
)
def test_letter_checks(profile, extra, problem):
    assert problem in letter_problems(_letter(extra), KNOWN, profile.checks)


def test_letter_word_count(profile):
    assert letter_problems(_letter(), KNOWN, profile.checks) == []
    assert letter_problems(["Too short."], KNOWN, profile.checks) == ["2 words; write 300 to 420"]


# Profile parsing (shared with the backend's upload validation)


def test_duplicate_fact_id():
    bank = (
        "- {id: a, section: experience, entry: e, text: t, tags: [], on_master_cv: false, approved: true}\n"
        * 2
    )
    with pytest.raises(ProfileError, match="duplicate id a"):
        parse_fact_bank(bank)


def test_checks_name_unknown_ids(profile):
    with pytest.raises(ProfileError, match="never_on_cv names ids not in the fact bank: nope"):
        parse_checks(
            profile.checks_yaml.replace("never_on_cv: [exp.cardly.5]", "never_on_cv: [nope]"), profile.facts
        )
    with pytest.raises(ProfileError, match="lacks role_types"):
        parse_checks("banned_words: []\nscope_words: []\ncut_order: []\nnever_on_cv: []", profile.facts)


def test_bad_checks_shapes_are_profile_errors(profile):
    listed = "bullet_bounds: [1]\n" + profile.checks_yaml.replace("bullet_bounds:", "old_bounds:")
    with pytest.raises(ProfileError, match="bullet_bounds must map"):
        parse_checks(listed, profile.facts)
    text = profile.checks_yaml.replace("projects_under_education: true", "projects_under_education: maybe")
    with pytest.raises(ProfileError, match="projects_under_education must be true or false"):
        parse_checks(text, profile.facts)


# A capitalized word first in a sentence is still a name.


@pytest.mark.parametrize(
    "text",
    [
        "Kafka pipelines in Python processing 2M rows",
        "Python jobs processing 2M rows; Kafka handled the rest",
    ],
)
def test_invented_name_first_in_a_sentence(profile, text):
    source = "Wrote Python jobs processing 2M rows"
    assert reword_problem(source, text, profile.checks) == ("fact_changed", "adds kafka")


def test_ordinary_openers_are_not_names():
    assert names("Built the app. Building more. Led it; helped it. The end.") == set()
    assert names("Kafka pipelines in Python processing 2M rows") == {"kafka", "python", "2m"}


def test_letter_sentence_opening_with_an_unknown_name(profile):
    problems = letter_problems(_letter(". Google taught me to ship."), KNOWN, profile.checks)
    assert "names what the fact bank and posting don't: google" in problems
