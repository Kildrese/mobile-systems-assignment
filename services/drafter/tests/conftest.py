import os
from pathlib import Path

import pytest

os.environ["DRAFTER_TOKEN"] = "drafter-test-token"
os.environ["ANTHROPIC_API_KEY"] = "anthropic-test-key"

from agentkit.cv.layout import Master
from agentkit.cv.profile import parse_checks, parse_fact_bank

FIXTURES = Path(__file__).parent / "fixtures"
# Kilian's real profile, when it's on this machine (never in CI or git).
PRIVATE = Path(__file__).parents[3] / "private" / "applicant"


class Profile:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.cv = (folder / "cv.docx").read_bytes()
        self.fact_bank = (folder / "fact_bank.yaml").read_text()
        self.rules = (folder / "rules.md").read_text()
        self.checks_yaml = (folder / "checks.yaml").read_text()
        self.master = Master(self.cv)
        self.facts = parse_fact_bank(self.fact_bank)
        self.checks = parse_checks(self.checks_yaml, self.facts)


@pytest.fixture(scope="session")
def profile() -> Profile:
    return Profile(FIXTURES)


@pytest.fixture(scope="session")
def real_profile() -> Profile:
    if not (PRIVATE / "checks.yaml").exists():
        pytest.skip("the real profile is not on this machine")
    return Profile(PRIVATE)
