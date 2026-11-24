"""``configs/models.yaml``: the model list, pinned digests and sampling defaults (P3.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from toolproof.agent.llm import OllamaAdapter
from toolproof.agent.loop import AgentLimits
from toolproof.paths import configs_dir


class ModelDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(ge=0.0, le=2.0)
    max_steps: int = Field(ge=1)
    max_wall_seconds: float = Field(gt=0)
    max_output_tokens: int = Field(ge=1)
    num_ctx: int = Field(ge=1024)

    def limits(self) -> AgentLimits:
        return AgentLimits(
            max_steps=self.max_steps,
            max_wall_seconds=self.max_wall_seconds,
            max_output_tokens=self.max_output_tokens,
        )


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    parameters: str


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: ModelDefaults
    models: dict[str, ModelEntry]
    ollama_version: str

    def resolve(self, key_or_name: str) -> ModelEntry:
        """Look a model up by role (``small``) or by Ollama name (``qwen2.5:3b``)."""
        if key_or_name in self.models:
            return self.models[key_or_name]
        for entry in self.models.values():
            if entry.name == key_or_name:
                return entry
        raise KeyError(f"model {key_or_name!r} is not in configs/models.yaml")

    def adapter(self, key_or_name: str, **kwargs: Any) -> OllamaAdapter:
        entry = self.resolve(key_or_name)
        return OllamaAdapter(entry.name, extra_options={"num_ctx": self.defaults.num_ctx}, **kwargs)


def load_models_config(path: Path | None = None) -> ModelsConfig:
    path = path or configs_dir() / "models.yaml"
    return ModelsConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def digest_matches(entry: ModelEntry, live_digest: str | None) -> bool:
    """Ollama reports digests with or without a ``sha256:`` prefix."""
    return live_digest is not None and live_digest.removeprefix("sha256:") == entry.digest
