"""WebSocket messages (PRD section 7), mirroring contracts/ws-messages.schema.json.

Incoming invokes are checked as strictly as the schema; backend/tests check the contract
fixtures against these models and every reply against the schema, so drift fails CI.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

NonEmpty = Annotated[str, StringConstraints(min_length=1)]
Base64 = Annotated[str, StringConstraints(
    min_length=4, pattern=r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")]


class Media(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mime: str
    b64: Base64


class Frame(Media):
    mime: Literal["image/jpeg"]


class Audio(Media):
    mime: Literal["audio/wav"]


class Invoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["invoke"]
    request_id: NonEmpty
    session_id: NonEmpty
    frame: Frame
    audio: Optional[Audio] = None
    text: Optional[NonEmpty] = None

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
