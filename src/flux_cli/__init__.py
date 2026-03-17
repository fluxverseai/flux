"""Flux CLI - Personal control plane for AI agent tooling."""

try:
    from importlib.metadata import version

    __version__ = version("flux-cli")
except Exception:
    __version__ = "0.1.0"
