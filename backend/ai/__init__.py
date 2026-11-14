"""Backend AI module: page reading, source text loading, book reasoning, and image generation."""

from .image import draw, cleanup_session, get_image, format_display_prompt, StubImageClient
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
    "draw",
    "cleanup_session",
    "get_image",
    "format_display_prompt",
    "StubImageClient",
    "NemotronClient",
    "NoTextFoundError",
    "PageReadError",
    "PageReadTimeoutError",
    "StubNemotronClient",
    "extract_frame_data",
    "read_page",
]
