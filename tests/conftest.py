from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from toolproof.env.docs_index import DocsIndex, load_docs_index
from toolproof.env.sandbox import Sandbox
from toolproof.env.tools.base import ToolContext
from toolproof.env.world import World, build_base_db
from toolproof.paths import docs_dir, seed_dir


@pytest.fixture(scope="session")
def base_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The world database built once per test session from the committed seed CSVs."""
    return build_base_db(seed_dir(), tmp_path_factory.mktemp("base") / "world.sqlite")


@pytest.fixture(scope="session")
def docs() -> DocsIndex:
    return load_docs_index(docs_dir())


@pytest.fixture
def world(base_db: Path, tmp_path: Path) -> Iterator[World]:
    with World.fresh(tmp_path / "trial", base_db=base_db) as trial_world:
        yield trial_world


@pytest.fixture
def ctx(world: World, docs: DocsIndex) -> ToolContext:
    return ToolContext(world=world, docs=docs)


@pytest.fixture
def sandbox(base_db: Path, docs: DocsIndex, tmp_path: Path) -> Iterator[Sandbox]:
    with Sandbox.open(tmp_path / "sandbox", base_db=base_db, docs=docs) as box:
        yield box
