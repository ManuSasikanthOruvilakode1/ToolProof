"""Filesystem locations used by the sandbox.

The data directory defaults to ``<project root>/data`` and can be overridden with the
``TOOLPROOF_DATA_DIR`` environment variable (used by Docker and by some tests).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get("TOOLPROOF_DATA_DIR")
    return Path(override) if override else PROJECT_ROOT / "data"


def seed_dir() -> Path:
    return data_dir() / "seed"


def docs_dir() -> Path:
    return data_dir() / "docs"


def base_db_path() -> Path:
    return data_dir() / "world.sqlite"


def configs_dir() -> Path:
    return PROJECT_ROOT / "configs"


def prompts_dir() -> Path:
    return configs_dir() / "prompts"


def results_dir() -> Path:
    override = os.environ.get("TOOLPROOF_RESULTS_DIR")
    return Path(override) if override else PROJECT_ROOT / "results"


def runs_dir() -> Path:
    return results_dir() / "runs"
