"""Backend AI module: page reading, source text, book session and reasoning, image generation."""

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
from .page_reader import (
    NemotronClient,
    NoTextFoundError,
    PageReadError,
    PageReadTimeoutError,
    StubNemotronClient,
    extract_frame_data,
    read_page,
)

__all__ = [
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
    "NemotronClient",
    "NoTextFoundError",
    "PageReadError",
    "PageReadTimeoutError",
    "StubNemotronClient",
    "extract_frame_data",
    "read_page",
]
