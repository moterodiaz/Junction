"""WebSocket messages, following the draft schema in PRD section 7.

Switch to the schema in contracts/ once issue #24 lands.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class Media(BaseModel):
    mime: str
    b64: str


class Invoke(BaseModel):
    type: Literal["invoke"]
    request_id: str
    session_id: str
    frame: Media
    audio: Optional[Media] = None
    text: Optional[str] = None

    @model_validator(mode="after")
    def audio_or_text(self) -> "Invoke":
        if (self.audio is None) == (self.text is None):
            raise ValueError("invoke needs exactly one of audio or text")
        return self


Stage = Literal["transcribing", "reading", "thinking", "drawing"]


class Status(BaseModel):
    type: Literal["status"] = "status"
    request_id: str
    stage: Stage


class Book(BaseModel):
    title: str
    author: str
    location: str


class Source(BaseModel):
    title: str
    url: str


class Card(BaseModel):
    type: Literal["card"] = "card"
    request_id: str
    title: str
    caption: str
    image_url: Optional[str]
    speech_text: str
    audio_url: Optional[str] = None
    book: Book
    sources: list[Source]
    models: dict[str, str]


ErrorCode = Literal["no_text_found", "stt_failed", "model_timeout", "internal"]


class Error(BaseModel):
    type: Literal["error"] = "error"
    request_id: Optional[str]
    code: ErrorCode
    message: str
    retryable: bool
