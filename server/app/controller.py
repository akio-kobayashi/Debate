from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from .config import Settings
from .documents import build_analysis_docx, build_reference_docx
from .google_workspace import GoogleWorkspaceClient
from .ollama_client import GenerationStopped, OllamaClient, OllamaError
from .prompts import build_analysis_messages, build_messages, build_reference_messages
from .state import DebateSession, SessionStore, TURN_PLAN, now_iso
from .survey import aggregate_responses, normalize_responses
from .theme_context import extract_theme_context


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
        self.google = GoogleWorkspaceClient(settings)
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
            task = session.generation_task or session.operation_task
            if task is None or task.done():
                return session
            session.stop_requested.set()
            task.cancel()
            if session.generation_task is not None:
                session.status = "stopping"
            session.updated_at = now_iso()
        await self.publish(session, "stopping", {"state": session.public()})
        return session

    async def reset(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.generation_task and not session.generation_task.done():
                session.stop_requested.set()
                session.generation_task.cancel()
            if session.operation_task and not session.operation_task.done():
                session.stop_requested.set()
                session.operation_task.cancel()
            session.status = "ready"
            session.next_turn = 0
            session.current_speaker = None
            session.current_kind = None
            session.current_text = ""
            session.theme_context = {}
            session.messages.clear()
            session.reference_status = "not_started"
            session.reference_data = {}
            session.reference_drive = {}
            session.survey_status = "not_started"
            session.survey_started_at = None
            session.survey_analysis = {}
            session.survey_drive = {}
            session.survey_error = None
            session.error_message = None
            session.updated_at = now_iso()
        await self.publish(session, "state", session.public())
        return session

    async def start_reference(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.status != "finished":
                raise ControllerError("reference can be generated after the debate finishes")
            if session.reference_status == "generating":
                raise SessionBusy("reference generation is already running")
            if not await self.gate.reserve():
                raise ServerBusy("another LLM generation is already running")
            session.reference_status = "generating"
            session.survey_error = None
            session.stop_requested.clear()
            session.operation_task = asyncio.create_task(self._run_reference(session))
        await self.publish(session, "reference_started", {"state": session.public()})
        return session

    async def start_survey(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.status != "finished":
                raise ControllerError("survey can start after the debate finishes")
            if session.reference_status != "uploaded":
                raise ControllerError("save the reference document before starting the survey")
            session.survey_status = "collecting"
            session.survey_started_at = now_iso()
            session.survey_analysis = {}
            session.survey_drive = {}
            session.survey_error = None
            session.updated_at = now_iso()
        await self.publish(session, "survey_started", {"state": session.public()})
        return session

    async def start_survey_analysis(self, debate_id: str) -> DebateSession:
        session = await self.get(debate_id)
        async with session.lock:
            if session.status != "finished":
                raise ControllerError("survey analysis requires a finished debate")
            if session.survey_status != "collecting" or not session.survey_started_at:
                raise ControllerError("start the survey before analyzing responses")
            if session.operation_task and not session.operation_task.done():
                raise SessionBusy("another survey operation is already running")
            if not await self.gate.reserve():
                raise ServerBusy("another LLM generation is already running")
            session.survey_status = "analyzing"
            session.survey_error = None
            session.stop_requested.clear()
            session.operation_task = asyncio.create_task(self._run_survey_analysis(session))
        await self.publish(session, "survey_analysis_started", {"state": session.public()})
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

    async def _collect_chat(
        self,
        messages: list[dict[str, str]],
        stop_requested: asyncio.Event,
    ) -> str:
        chunks: list[str] = []
        async for token, _chunk in self.ollama.stream_chat(messages, stop_requested):
            if stop_requested.is_set():
                raise GenerationStopped
            chunks.append(token)
        text = "".join(chunks).strip()
        if not text:
            raise OllamaError("Ollama returned an empty message")
        return text

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`").replace("json\n", "", 1).strip()
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise OllamaError("LLM did not return a JSON object")
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OllamaError("LLM returned invalid reference JSON") from exc
        if not isinstance(value, dict):
            raise OllamaError("LLM reference result must be an object")
        return value

    async def _run_reference(self, session: DebateSession) -> None:
        try:
            raw_reference = await self._collect_chat(
                build_reference_messages(session), session.stop_requested
            )
            reference = self._parse_json(raw_reference)
            session.reference_data = reference
            await self.publish(session, "reference_ready", {"state": session.public()})
            document = await asyncio.to_thread(
                build_reference_docx, session.theme, reference
            )
            drive = await asyncio.to_thread(
                self.google.upload_docx,
                document,
                f"Debate_{session.debate_id}_reference.docx",
            )
            session.reference_drive = drive
            session.reference_status = "uploaded"
            session.updated_at = now_iso()
            await self.publish(session, "reference_completed", {"state": session.public()})
        except asyncio.CancelledError:
            if session.status != "ready":
                session.reference_status = "error"
                session.survey_error = "reference generation was stopped"
                await self.publish(session, "reference_error", {"state": session.public()})
            raise
        except Exception as exc:
            session.reference_status = "error"
            session.survey_error = str(exc)
            session.updated_at = now_iso()
            await self.publish(session, "reference_error", {
                "message": session.survey_error,
                "state": session.public(),
            })
        finally:
            session.operation_task = None
            await self.gate.release()

    async def _run_survey_analysis(self, session: DebateSession) -> None:
        ended_at = now_iso()
        try:
            form, responses = await asyncio.to_thread(
                self.google.fetch_responses,
                session.survey_started_at or ended_at,
                ended_at,
            )
            normalized = normalize_responses(
                form,
                responses,
                session.survey_started_at or ended_at,
                ended_at,
            )
            aggregate = aggregate_responses(normalized)
            await self.publish(session, "survey_aggregated", {
                "respondent_count": aggregate["respondent_count"],
                "state": session.public(),
            })
            interpretation = await self._collect_chat(
                build_analysis_messages(session, aggregate), session.stop_requested
            )
            aggregate["interpretation"] = interpretation
            session.survey_analysis = aggregate
            document = await asyncio.to_thread(
                build_analysis_docx, session.theme, aggregate
            )
            drive = await asyncio.to_thread(
                self.google.upload_docx,
                document,
                f"Debate_{session.debate_id}_survey_analysis.docx",
            )
            session.survey_drive = drive
            session.survey_status = "completed"
            session.survey_error = None
            session.updated_at = now_iso()
            await self.publish(session, "survey_analysis_completed", {"state": session.public()})
        except asyncio.CancelledError:
            if session.status != "ready":
                session.survey_status = "error"
                session.survey_error = "survey analysis was stopped"
                await self.publish(session, "survey_analysis_error", {"state": session.public()})
            raise
        except Exception as exc:
            session.survey_status = "error"
            session.survey_error = str(exc)
            session.updated_at = now_iso()
            await self.publish(session, "survey_analysis_error", {
                "message": session.survey_error,
                "state": session.public(),
            })
        finally:
            session.operation_task = None
            await self.gate.release()

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
                "text": text,
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
