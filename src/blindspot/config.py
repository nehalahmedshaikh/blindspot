from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "current"
SITE_DATA_DIR = PROJECT_ROOT / "site" / "assets" / "data"


@dataclass(frozen=True)
class SeriesSpec:
    goal: int
    code: str
    cadence: int
    applicability: str
    rationale: str


@dataclass(frozen=True)
class Country:
    alpha2: str
    alpha3: str
    m49: str
    name: str


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_series() -> list[SeriesSpec]:
    return [SeriesSpec(**item) for item in _read_json(CONFIG_DIR / "series.json")]


def load_goals() -> list[dict[str, Any]]:
    return _read_json(CONFIG_DIR / "goals.json")


def load_countries() -> list[Country]:
    return [Country(**item) for item in _read_json(CONFIG_DIR / "countries.json")]


def ensure_directories() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
