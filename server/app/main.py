from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .controller import (
    ControllerError,
    DebateController,
    event_stream,
)


class ThemeRequest(BaseModel):
    theme: str = Field(min_length=1, max_length=2000)


app = FastAPI(title="Debate Demo API", version="0.1.0")
controller = DebateController(settings)


def handle_controller_error(exc: ControllerError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model": settings.ollama_model,
        "overlay_provider": settings.overlay_provider,
        "ollama": "ok" if await controller.ollama.health() else "unavailable",
    }


@app.post("/api/debates", status_code=201)
async def create_debate(request: ThemeRequest) -> dict[str, Any]:
    try:
        session = await controller.create(request.theme)
    except ControllerError as exc:
        raise handle_controller_error(exc) from exc
    return session.public()


@app.get("/api/debates/{debate_id}")
async def get_debate(debate_id: str) -> dict[str, Any]:
    try:
        return (await controller.get(debate_id)).public()
    except ControllerError as exc:
        raise handle_controller_error(exc) from exc


@app.get("/api/debates/{debate_id}/events")
async def debate_events(request: Request, debate_id: str) -> StreamingResponse:
    try:
        await controller.get(debate_id)
    except ControllerError as exc:
        raise handle_controller_error(exc) from exc
    return StreamingResponse(
        event_stream(controller, debate_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/debates/{debate_id}/next", status_code=202)
async def next_turn(debate_id: str) -> dict[str, Any]:
    try:
        session = await controller.start_next(debate_id)
    except ControllerError as exc:
        raise handle_controller_error(exc) from exc
    return {
        "status": "accepted",
        "debate_id": session.debate_id,
        "turn_index": session.next_turn,
        "speaker": session.current_speaker,
        "kind": session.current_kind,
    }


@app.post("/api/debates/{debate_id}/stop")
async def stop_debate(debate_id: str) -> dict[str, Any]:
    try:
        return (await controller.stop(debate_id)).public()
    except ControllerError as exc:
        raise handle_controller_error(exc) from exc


@app.post("/api/debates/{debate_id}/reset")
async def reset_debate(debate_id: str) -> dict[str, Any]:
    try:
        return (await controller.reset(debate_id)).public()
    except ControllerError as exc:
        raise handle_controller_error(exc) from exc


demo_dir = Path(__file__).resolve().parents[2] / "demo"
if demo_dir.is_dir():
    app.mount("/", StaticFiles(directory=demo_dir, html=True), name="demo")
