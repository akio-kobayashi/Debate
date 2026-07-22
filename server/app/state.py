from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


TURN_PLAN: list[tuple[str, str]] = [
    ("C", "define"),
    ("A", "opening"),
    ("B", "opening"),
    ("C", "organize"),
    ("A", "rebuttal"),
    ("B", "rebuttal"),
    ("A", "closing"),
    ("B", "closing"),
    ("C", "summary"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DebateMessage:
    message_id: str
    speaker: str
    turn_index: int
    kind: str
    text: str
    status: str = "completed"
    created_at: str = field(default_factory=now_iso)


@dataclass
class DebateSession:
    debate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    theme: str = ""
    model: str = ""
    status: str = "ready"
    next_turn: int = 0
    current_speaker: str | None = None
    current_kind: str | None = None
    current_text: str = ""
    theme_context: dict[str, Any] = field(default_factory=dict)
    messages: list[DebateMessage] = field(default_factory=list)
    error_message: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    subscribers: set[asyncio.Queue[str]] = field(default_factory=set, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    stop_requested: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    generation_task: asyncio.Task[Any] | None = field(default=None, repr=False)
    event_sequence: int = field(default=0, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "debate_id": self.debate_id,
            "theme": self.theme,
            "model": self.model,
            "status": self.status,
            "next_turn": self.next_turn,
            "total_turns": len(TURN_PLAN),
            "current_speaker": self.current_speaker,
            "current_kind": self.current_kind,
            "current_text": self.current_text,
            "theme_context": self.theme_context,
            "messages": [asdict(message) for message in self.messages],
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, DebateSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, theme: str, model: str) -> DebateSession:
        session = DebateSession(theme=theme, model=model)
        async with self._lock:
            self._sessions[session.debate_id] = session
        return session

    async def get(self, debate_id: str) -> DebateSession | None:
        async with self._lock:
            return self._sessions.get(debate_id)

    async def remove(self, debate_id: str) -> None:
        async with self._lock:
            self._sessions.pop(debate_id, None)
