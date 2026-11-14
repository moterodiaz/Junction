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
            raw = await websocket.receive_text()
            await handle(websocket, raw)
    except WebSocketDisconnect:
        pass


async def handle(websocket: WebSocket, raw: str) -> None:
    request_id = None
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("request_id"), str):
            request_id = data["request_id"]
        invoke = Invoke.model_validate(data)
    except (ValueError, ValidationError) as exc:
        await send(websocket, Error(request_id=request_id, code="internal",
                                    message=f"invalid invoke: {exc}", retryable=False))
        return

    async def send_stage(stage: Stage) -> None:
        await send(websocket, Status(request_id=invoke.request_id, stage=stage))

    try:
        card = await pipeline.run(invoke, send_stage)
    except WebSocketDisconnect:
        raise
    except pipeline.PipelineError as exc:
        log.info("request %s failed: %s", invoke.request_id, exc.code)
        await send(websocket, Error(request_id=invoke.request_id, code=exc.code,
                                    message=exc.message, retryable=exc.retryable))
        return
    except Exception:
        log.exception("pipeline failed for %s", invoke.request_id)
        await send(websocket, Error(request_id=invoke.request_id, code="internal",
                                    message="Something went wrong. Try again.", retryable=True))
        return
    await send(websocket, card)


async def send(websocket: WebSocket, message) -> None:
    await websocket.send_text(message.model_dump_json())
