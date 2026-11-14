"""FastAPI orchestrator. Run locally from backend/: uvicorn app.main:app --reload"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ai.image import image_router
from ai.page_reader import PageReadError
from stt.speak import audio_router

from . import pipeline
from .config import get_settings
from .latency import StageTimer
from .messages import Error, Invoke, Stage, Status

log = logging.getLogger("metalab")
if not log.handlers:
    # uvicorn leaves app loggers unconfigured (WARNING, no handler), which hides the INFO latency summaries.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)

app = FastAPI(title="MetaLab backend")
app.include_router(audio_router)
if image_router is not None:
    app.include_router(image_router)


def create_app(require_keys: bool = False) -> FastAPI:
    """The app to serve. A deploy passes require_keys=True so a missing secret fails at
    startup, naming every missing key; local runs and tests stay keyless (offline stubs)."""
    if require_keys:
        get_settings()
    return app


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Handle one request at a time, but keep listening while it runs: a disconnect cancels
    the request (no further model calls, nothing saved to the book session), and a message
    that arrives meanwhile is handled next (#111)."""
    await websocket.accept()
    receiving: asyncio.Task | None = None
    try:
        while True:
            receiving = receiving or asyncio.create_task(websocket.receive())
            event = await receiving
            receiving = None
            if event["type"] == "websocket.disconnect":
                break
            raw = event.get("text")
            if raw is None:
                raw = event.get("bytes")  # the iPhone client sends JSON as binary frames
            if raw is None:
                continue
            handling = asyncio.create_task(handle(websocket, raw))
            receiving = asyncio.create_task(websocket.receive())
            await asyncio.wait({handling, receiving}, return_when=asyncio.FIRST_COMPLETED)
            if receiving.done() and receiving.result()["type"] == "websocket.disconnect":
                handling.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await handling
                break
            await handling  # a new message (if any) waits in `receiving` for the next turn
    except WebSocketDisconnect:
        pass
    finally:
        if receiving is not None and not receiving.done():
            receiving.cancel()


async def handle(websocket: WebSocket, raw: str | bytes) -> None:
    request_id = None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")  # contract is UTF-8 JSON; don't let json.loads sniff UTF-16/32
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("request_id"), str) and data["request_id"]:
            request_id = data["request_id"]
        invoke = Invoke.model_validate(data)
    except ValidationError as exc:
        # Field locations and messages only: never the input, which carries user text and base64 media.
        log.warning("invalid invoke %s: %s", request_id,
                    exc.errors(include_url=False, include_context=False, include_input=False))
        await reject(websocket, request_id)
        return
    except (ValueError, RecursionError) as exc:
        log.warning("unparseable message: %s", type(exc).__name__)
        await reject(websocket, request_id)
        return

    timer = StageTimer(invoke.request_id)
    outcome = "error"

    async def send_stage(stage: Stage) -> None:
        timer.start(stage)
        await send(websocket, Status(request_id=invoke.request_id, stage=stage))

    try:
        card = await pipeline.run(invoke, send_stage)
        await send(websocket, card)
        outcome = "card"
    except asyncio.CancelledError:
        outcome = "cancelled"  # the phone hung up mid-request
        raise
    except WebSocketDisconnect:
        outcome = "disconnected"
        raise
    except pipeline.PipelineError as exc:
        log.info("request %s failed: %s", invoke.request_id, exc.code)
        await send(websocket, Error(request_id=invoke.request_id, code=exc.code,
                                    message=exc.message, retryable=exc.retryable))
        return
    except PageReadError as exc:
        pipeline.log_failure("page reading failed for %s", exc, invoke.request_id)
        messages = {
            "no_text_found": "No readable text was found on the page.",
            "model_timeout": "Page reading timed out. Try again.",
            "internal": "Page reading failed. Try again.",
        }
        code = exc.code if exc.code in messages else "internal"  # unknown codes still reach the phone
        await send(websocket, Error(request_id=invoke.request_id, code=code,
                                    message=messages[code], retryable=exc.retryable))
        return
    except Exception as exc:
        pipeline.log_failure("pipeline failed for %s", exc, invoke.request_id)
        await send(websocket, Error(request_id=invoke.request_id, code="internal",
                                    message="Something went wrong. Try again.", retryable=True))
        return
    finally:
        timer.log(outcome)


async def reject(websocket: WebSocket, request_id: str | None) -> None:
    await send(websocket, Error(request_id=request_id, code="internal",
                                message="Invalid request.", retryable=False))


async def send(websocket: WebSocket, message) -> None:
    await websocket.send_text(message.model_dump_json())
