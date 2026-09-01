"""A suite of AI-powered command-line tools for text correction, audio transcription, and voice assistance."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    __version__: str


def __getattr__(name: str) -> str:
    """Resolve `__version__` lazily; reading distribution metadata costs ~29ms."""
    if name == "__version__":
        from importlib.metadata import version  # noqa: PLC0415

        return version("agent-cli")
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
