"""FastAPI orchestrator. Run locally from backend/: uvicorn app.main:app --reload"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from . import pipeline
from .messages import Error, Invoke, Stage, Status

log = logging.getLogger("metalab")

app = FastAPI(title="MetaLab backend")


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            event = await websocket.receive()
            if event["type"] == "websocket.disconnect":
                break
            raw = event.get("text")
            if raw is None:
                raw = event.get("bytes")  # the iPhone client sends JSON as binary frames
            if raw is None:
                continue
            await handle(websocket, raw)
    except WebSocketDisconnect:
        pass


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

    async def send_stage(stage: Stage) -> None:
        await send(websocket, Status(request_id=invoke.request_id, stage=stage))

    try:
        card = await pipeline.run(invoke, send_stage)
    except WebSocketDisconnect:
        raise
    except Exception:
        log.exception("pipeline failed for %s", invoke.request_id)
        await send(websocket, Error(request_id=invoke.request_id, code="internal",
                                    message="Something went wrong. Try again.", retryable=True))
        return
    await send(websocket, card)


async def reject(websocket: WebSocket, request_id: str | None) -> None:
    await send(websocket, Error(request_id=request_id, code="internal",
                                message="Invalid request.", retryable=False))


async def send(websocket: WebSocket, message) -> None:
    await websocket.send_text(message.model_dump_json())
