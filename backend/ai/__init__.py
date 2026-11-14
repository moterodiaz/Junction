"""Backend AI module for MetaLab (PRD section 2, section 4, section 8).

Exports the public-domain play text loader and passage locator.
Gracefully re-exports other sibling AI modules if present in the tree.
"""

from __future__ import annotations

from .source_loader import (
    Act,
    Line,
    PassageMatch,
    Play,
    Scene,
    find_passage,
    get_play,
    get_source_citation,
    list_plays,
    load_play,
    locate_passage,
    set_plays_directory,
)

__all__ = [
    "Act",
    "Line",
    "PassageMatch",
    "Play",
    "Scene",
    "find_passage",
    "get_play",
    "get_source_citation",
    "list_plays",
    "load_play",
    "locate_passage",
    "set_plays_directory",
]

# Optional sibling module exports if present on branch
try:
    from .page_reader import read_page  # type: ignore
    __all__.append("read_page")
except ImportError:
    pass

try:
    from .reasoning import think  # type: ignore
    __all__.append("think")
except ImportError:
    pass

try:
    from .image import draw  # type: ignore
    __all__.append("draw")
except ImportError:
    pass
