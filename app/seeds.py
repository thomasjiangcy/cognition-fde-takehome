from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SEEDS_DIRECTORY = Path(__file__).with_name("seeds")


@dataclass(frozen=True)
class SeedLabel:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class SeedIssue:
    key: str
    title: str
    body_path: Path
    labels: tuple[SeedLabel, ...]
    repo_labels: tuple[SeedLabel, ...] = ()

    def render_body(self) -> str:
        return self.body_path.read_text(encoding="utf-8").removesuffix("\n")


BUG_INVESTIGATION_REPO_LABELS: tuple[SeedLabel, ...] = (
    SeedLabel(
        name="validation:validated",
        color="4F9031",
        description="A committer has validated / submitted the issue or it was reported by multiple users",
    ),
    SeedLabel(
        name="#bug:cant-reproduce",
        color="ededed",
        description="Bugs that cannot be reproduced",
    ),
    SeedLabel(
        name="devin:assigned",
        color="0E8A16",
        description="A Devin session has been assigned to handle this issue",
    ),
)

SEED_CATALOG: dict[str, SeedIssue] = {
    "mixed-chart-matrixify": SeedIssue(
        key="apache-superset-39007",
        title="6.1.0rc1 - matrixify not applying to query B in Mixed Chart",
        body_path=SEEDS_DIRECTORY / "mixed-chart-matrixify.md",
        labels=(
            SeedLabel(
                name="validation:required",
                color="D93F0B",
                description="A committer should validate the issue",
            ),
        ),
        repo_labels=BUG_INVESTIGATION_REPO_LABELS,
    ),
    "dashboard-label-colors": SeedIssue(
        key="apache-superset-40708",
        title="Some dashboard charts intermittently fall back to color_scheme instead of label_colors on initial render",
        body_path=SEEDS_DIRECTORY / "dashboard-label-colors.md",
        labels=(
            SeedLabel(
                name="validation:required",
                color="D93F0B",
                description="A committer should validate the issue",
            ),
            SeedLabel(
                name="dashboard:colors",
                color="3CC4E6",
                description="Related to the color scheme of the Dashboard",
            ),
        ),
        repo_labels=BUG_INVESTIGATION_REPO_LABELS,
    ),
}
