"""Backend AI module: page reading, source text, book session and reasoning, image generation."""

from __future__ import annotations

# Page reader (PRD Section 4, Issue #28)
try:
    from .page_reader import (
        GeminiPageReader,
        NemotronClient,
        NoTextFoundError,
        PageReadError,
        PageReadTimeoutError,
        PageText,
        StubGeminiPageReader,
        StubNemotronClient,
        extract_frame_data,
        read_page,
        read_page_with_fallback,
    )
except ImportError:
    pass

# Image generation and serving (PRD Section 4, Section 6, Section 9)
from .image import draw, cleanup_session, get_image, format_display_prompt, StubImageClient

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
from .session import (
    BookInfo,
    BookSession,
    QAExchange,
    SessionStore,
    default_session_store,
)
from .reasoning import (
    DEFAULT_MODEL_REASON,
    GeminiReasoningClient,
    HttpGeminiClient,
    ReasoningError,
    StubGeminiClient,
    get_reasoning_client,
    parse_reasoning_json,
    set_reasoning_client,
    think,
)

# Optional sibling modules if present
try:
    from .reasoning import think  # type: ignore
except ImportError:
    pass

__all__ = [
    # Page reading
    "GeminiPageReader",
    "NemotronClient",
    "NoTextFoundError",
    "PageReadError",
    "PageReadTimeoutError",
    "PageText",
    "StubGeminiPageReader",
    "StubNemotronClient",
    "extract_frame_data",
    "read_page",
    "read_page_with_fallback",
    # Image generation
    "draw",
    "cleanup_session",
    "get_image",
    "format_display_prompt",
    "StubImageClient",
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
    # Book session and reasoning
    "BookInfo",
    "BookSession",
    "QAExchange",
    "SessionStore",
    "default_session_store",
    "DEFAULT_MODEL_REASON",
    "GeminiReasoningClient",
    "HttpGeminiClient",
    "ReasoningError",
    "StubGeminiClient",
    "get_reasoning_client",
    "parse_reasoning_json",
    "set_reasoning_client",
    "think",
]
