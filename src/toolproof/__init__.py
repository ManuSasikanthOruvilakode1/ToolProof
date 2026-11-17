"""ToolProof: a reproducible benchmark and regression harness for LLM agent tool use."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("toolproof")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
