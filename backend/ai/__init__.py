"""Backend AI module: page reading, source text loading, book reasoning, and image generation."""

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
    "NemotronClient",
    "NoTextFoundError",
    "PageReadError",
    "PageReadTimeoutError",
    "StubNemotronClient",
    "extract_frame_data",
    "read_page",
]
