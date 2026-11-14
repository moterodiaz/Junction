"""Backend AI module: page reading, source text loading, book reasoning, and image generation."""

from __future__ import annotations

# Page reader (PRD Section 4, Issue #28)
try:
    from .page_reader import (
        NemotronClient,
        NoTextFoundError,
        PageReadError,
        PageReadTimeoutError,
        StubNemotronClient,
        extract_frame_data,
        read_page,
    )
except ImportError:
    pass

# Source text loader (PRD Section 2, Section 8, Section 10 C4, Issue #29)
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

# Optional sibling modules if present
try:
    from .reasoning import think  # type: ignore
except ImportError:
    pass

try:
    from .image import draw  # type: ignore
except ImportError:
    pass

__all__ = [
    # Page reading
    "NemotronClient",
    "NoTextFoundError",
    "PageReadError",
    "PageReadTimeoutError",
    "StubNemotronClient",
    "extract_frame_data",
    "read_page",
    # Source text loader
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
