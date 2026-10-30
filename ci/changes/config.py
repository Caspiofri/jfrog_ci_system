"""Loads config/tracked_pages.yaml: the pages change detection reads, per competitor, and the D13 axes each informs."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator

from config.settings import CONFIG_DIR

TRACKED_PAGES_PATH = CONFIG_DIR / "tracked_pages.yaml"
JFROG = "jfrog"  # the head-to-head baseline: tracked like a competitor, never a key in competitors.yaml

Axis = Literal["deployment", "package_coverage", "security_scanning", "curation_gating", "ai_mcp",
               "cicd_integration", "pricing_model"]
# the D13 axes, in matrix order, with the label the UI and the Changes items use
AXES: dict[str, str] = {
    "deployment": "Deployment",
    "package_coverage": "Package coverage",
    "security_scanning": "Security scanning",
    "curation_gating": "Curation/gating",
    "ai_mcp": "AI & MCP",
    "cicd_integration": "CI/CD integration",
    "pricing_model": "Pricing model",
}
PageType = Literal["pricing", "product", "docs"]


class TrackedPage(BaseModel):
    key: str  # unique within the competitor; names the snapshot folder
    url: str
    page_type: PageType
    axes: list[Axis]

    @field_validator("key")
    @classmethod
    def _key_is_a_path_part(cls, v: str) -> str:
        if not v or not v.replace("_", "").isalnum() or v != v.lower():
            raise ValueError(f"page key {v!r}: lowercase letters, digits and _ only")
        return v

    @field_validator("axes")
    @classmethod
    def _axes(cls, v: list[str]) -> list[str]:
        if not v or len(set(v)) != len(v):
            raise ValueError("axes must be a non-empty list without repeats")
        return v


class TrackedPages(BaseModel):
    competitors: dict[str, list[TrackedPage]]

    @model_validator(mode="after")
    def _one_source_per_cell(self) -> "TrackedPages":
        for competitor, pages in self.competitors.items():
            keys = [p.key for p in pages]
            if len(set(keys)) != len(keys):
                raise ValueError(f"{competitor}: page keys repeat")
            seen: dict[str, str] = {}
            for p in pages:
                for axis in p.axes:
                    if axis in seen:
                        raise ValueError(f"{competitor}: axis {axis} informed by both {seen[axis]} and {p.key}")
                    seen[axis] = p.key
        return self

    def pages(self, competitors: list[str] | None = None) -> list[tuple[str, TrackedPage]]:
        """(competitor, page) pairs in config order, optionally only for the given competitors."""
        return [(c, p) for c, pages in self.competitors.items() if competitors is None or c in competitors
                for p in pages]


def load(path: Path = TRACKED_PAGES_PATH) -> TrackedPages:
    return TrackedPages.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
