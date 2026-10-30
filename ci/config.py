"""Loads config/competitors.yaml: who we track, and where each source looks for them (D10)."""
from pathlib import Path

import yaml
from pydantic import BaseModel

from config.settings import CONFIG_DIR

COMPETITORS_PATH = CONFIG_DIR / "competitors.yaml"


class Feed(BaseModel):
    url: str
    # keep an entry only if its title or text contains one of these (case-insensitive); empty keeps everything.
    # Needed for broad feeds such as AWS What's New, where CodeArtifact is a small fraction.
    keywords: list[str] = []


class Competitor(BaseModel):
    key: str
    name: str
    news_queries: list[str] = []
    hn_queries: list[str] = []
    feeds: list[Feed] = []
    github_repos: list[str] = []  # "owner/repo"


class CIConfig(BaseModel):
    window_days: int = 7
    competitors: list[Competitor]  # includes the Industry channel under key "industry"

    def by_key(self) -> dict[str, Competitor]:
        return {c.key: c for c in self.competitors}


def load(path: Path = COMPETITORS_PATH) -> CIConfig:
    return CIConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
