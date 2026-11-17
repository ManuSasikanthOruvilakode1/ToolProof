"""One trial's sandbox: a fresh world, the tool context and the toolbox, wired together."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from toolproof.env.docs_index import DocsIndex, load_docs_index
from toolproof.env.faults import FaultInjector
from toolproof.env.toolbox import ToolBox
from toolproof.env.tools import make_tools
from toolproof.env.tools.base import DescriptionLevel, ToolContext
from toolproof.env.world import Snapshot, World, WorldDiff


@dataclass
class Sandbox:
    world: World
    ctx: ToolContext
    toolbox: ToolBox
    initial: Snapshot

    @classmethod
    def open(
        cls,
        workdir: Path,
        *,
        base_db: Path | None = None,
        docs: DocsIndex | None = None,
        user_replies: Sequence[str] = (),
        faults: FaultInjector | None = None,
        n_distractors: int = 0,
        description_level: DescriptionLevel = "standard",
    ) -> Sandbox:
        world = World.fresh(workdir, base_db=base_db)
        ctx = ToolContext(
            world=world, docs=docs or load_docs_index(), user_replies=tuple(user_replies)
        )
        toolbox = ToolBox(
            make_tools(n_distractors), ctx, faults=faults, description_level=description_level
        )
        return cls(world=world, ctx=ctx, toolbox=toolbox, initial=world.snapshot())

    def diff(self) -> WorldDiff:
        """Changes made to the world since the sandbox was opened."""
        return self.initial.diff(self.world.snapshot())

    def close(self) -> None:
        self.world.close()

    def __enter__(self) -> Sandbox:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
