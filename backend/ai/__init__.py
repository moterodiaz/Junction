"""Backend AI module for MetaLab: book session and reasoning with Gemini."""

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
]
