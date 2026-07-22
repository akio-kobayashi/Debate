from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from .config import Settings
from .ollama_client import GenerationStopped, OllamaClient, OllamaError
from .prompts import build_messages
from .state import DebateSession, SessionStore, TURN_PLAN, now_iso


class ControllerError(RuntimeError):
    status_code = 400


class SessionNotFound(ControllerError):
    status_code = 404


class SessionBusy(ControllerError):
    status_code = 409


class ServerBusy(ControllerError):
    status_code = 429


class GenerationGate:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._busy = False

    async def reserve(self) -> bool:
        async with self._lock:
            if self._busy:
                return False
            self._busy = True
            return True

    async def release(self) -> None:
        async with self._lock:
            self._busy = False


class DebateController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SessionStore()
        self.ollama = OllamaClient(settings)
        self.gate = GenerationGate()

    async def create(self, theme: str) -> DebateSession:
        theme = theme.strip()
        if not theme:
            raise ControllerError("theme must not be empty")
        return await self.store.create(theme, self.settings.ollama_model)

    async def get(self, debate_id: str) -> DebateSession:
        session = await self.store.get(debate_id)
        if session is None:
            raise SessionNotFound("debate session not found")
        return session

    async def start_next(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.status == "generating":
                raise SessionBusy("this debate is already generating")
            if session.status == "stopping":
                raise SessionBusy("the previous generation is stopping")
            if session.status == "finished":
                raise ControllerError("debate is already finished")
            if session.next_turn >= len(TURN_PLAN):
                raise ControllerError("no turn remains")
            if not await self.gate.reserve():
                raise ServerBusy("another LLM generation is already running")
            session.status = "generating"
            session.current_speaker, session.current_kind = TURN_PLAN[session.next_turn]
            session.current_text = ""
            session.error_message = None
            session.stop_requested.clear()
            session.updated_at = now_iso()
            session.generation_task = asyncio.create_task(
                self._run_turn(session, session.next_turn, session.current_speaker, session.current_kind)
            )
        await self.publish(session, "turn_started", {
            "turn_index": session.next_turn,
            "speaker": session.current_speaker,
            "kind": session.current_kind,
            "state": session.public(),
        })
        return session

    async def stop(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.status != "generating" or session.generation_task is None:
                return session
            session.status = "stopping"
            session.stop_requested.set()
            session.generation_task.cancel()
            session.updated_at = now_iso()
        await self.publish(session, "stopping", {"state": session.public()})
        return session

    async def reset(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.generation_task and not session.generation_task.done():
                session.stop_requested.set()
                session.generation_task.cancel()
            session.status = "ready"
            session.next_turn = 0
            session.current_speaker = None
            session.current_kind = None
            session.current_text = ""
            session.theme_context = {}
            session.messages.clear()
            session.error_message = None
            session.updated_at = now_iso()
        await self.publish(session, "state", session.public())
        return session

    async def subscribe(self, debate_id: str) -> tuple[DebateSession, asyncio.Queue[str]]:
        session = await self.get(debate_id)
        queue: asyncio.Queue[str] = asyncio.Queue()
        session.subscribers.add(queue)
        return session, queue

    async def unsubscribe(self, session: DebateSession, queue: asyncio.Queue[str]) -> None:
        session.subscribers.discard(queue)

    async def publish(self, session: DebateSession, event: str, payload: dict[str, Any]) -> None:
        session.event_sequence += 1
        envelope = {
            "event": event,
            "id": session.event_sequence,
            "data": payload,
        }
        encoded = json.dumps(envelope, ensure_ascii=False)
        for queue in list(session.subscribers):
            queue.put_nowait(encoded)

    async def _run_turn(self, session: DebateSession, turn_index: int, speaker: str, kind: str) -> None:
        try:
            chunks: list[str] = []
            messages = build_messages(session, speaker, kind)
            async for token, _chunk in self.ollama.stream_chat(messages, session.stop_requested):
                chunks.append(token)
                session.current_text = "".join(chunks)
                session.updated_at = now_iso()
                await self.publish(session, "token", {
                    "turn_index": turn_index,
                    "speaker": speaker,
                    "text": token,
                })
            text = "".join(chunks).strip()
            if not text:
                raise OllamaError("Ollama returned an empty message")
            message = {
                "message_id": f"{session.debate_id}-{turn_index}",
                "speaker": speaker,
                "turn_index": turn_index,
                "kind": kind,
                "text": text[: self.settings.debate_max_chars],
                "status": "completed",
            }
            from .state import DebateMessage

            session.messages.append(DebateMessage(**message))
            if turn_index == 0 and speaker == "C":
                session.theme_context = extract_theme_context(text)
            session.next_turn = turn_index + 1
            session.current_speaker = None
            session.current_kind = None
            session.current_text = ""
            session.status = "finished" if session.next_turn >= len(TURN_PLAN) else "waiting"
            session.updated_at = now_iso()
            await self.publish(session, "turn_completed", {
                "turn_index": turn_index,
                "speaker": speaker,
                "kind": kind,
                "text": text,
                "state": session.public(),
            })
            if session.status == "finished":
                await self.publish(session, "debate_finished", {"state": session.public()})
        except GenerationStopped:
            await self._mark_stopped(session, turn_index)
        except asyncio.CancelledError:
            await self._mark_stopped(session, turn_index)
            raise
        except Exception as exc:
            session.status = "error"
            session.error_message = str(exc)
            session.current_speaker = None
            session.current_kind = None
            session.current_text = ""
            session.updated_at = now_iso()
            await self.publish(session, "error", {
                "message": session.error_message,
                "state": session.public(),
            })
        finally:
            session.generation_task = None
            await self.gate.release()

    async def _mark_stopped(self, session: DebateSession, turn_index: int) -> None:
        session.status = "waiting"
        session.current_speaker = None
        session.current_kind = None
        session.current_text = ""
        session.updated_at = now_iso()
        await self.publish(session, "turn_stopped", {
            "turn_index": turn_index,
            "state": session.public(),
        })


def extract_theme_context(text: str) -> dict[str, Any]:
    labels = {
        "motion": "議題（整理後）",
        "definitions": "用語の定義",
        "scope": "対象範囲・前提",
        "evaluation_axes": "主な評価観点",
        "current_issue": "現在の論点",
        "next_instruction": "次の指示",
    }
    result: dict[str, Any] = {}
    for key, label in labels.items():
        pattern = rf"{re.escape(label)}：?\\s*(.*?)(?=\\n[^\\n：]+：|\\Z)"
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            result[key] = match.group(1).strip()
    if "motion" not in result:
        result["motion"] = text[:300].strip()
    return result


async def event_stream(controller: DebateController, debate_id: str) -> AsyncIterator[str]:
    session, queue = await controller.subscribe(debate_id)
    try:
        yield format_sse("state", session.public(), session.event_sequence)
        while True:
            try:
                encoded = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            envelope = json.loads(encoded)
            yield format_sse(envelope["event"], envelope["data"], envelope["id"])
    except asyncio.CancelledError:
        raise
    finally:
        await controller.unsubscribe(session, queue)


def format_sse(event: str, data: dict[str, Any], event_id: int) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"
