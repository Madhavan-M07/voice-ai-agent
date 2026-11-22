"""Real-time voice AI agent."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("voice-agent")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0"
