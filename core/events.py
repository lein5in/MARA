from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class State(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    WAITING_CONFIRMATION = "waiting_confirmation"


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolStarted:
    id: str
    name: str
    args: dict


@dataclass
class ToolFinished:
    id: str
    name: str
    ok: bool
    duration: float
    summary: str


@dataclass
class ConfirmationRequested:
    id: str
    title: str
    description: str
    tool: str
    args: dict


@dataclass
class ConfirmationResolved:
    id: str
    accepted: bool


@dataclass
class StateChanged:
    state: State


@dataclass
class Visual:
    html: str
    title: str = ""


@dataclass
class Error:
    message: str


@dataclass
class TurnStarted:
    text: str
    source: str


@dataclass
class Done:
    text: str = ""


@dataclass
class ShowInterface:
    pass


@dataclass
class HideInterface:
    pass


@dataclass
class QuitRequested:
    pass


@dataclass
class ConversationReset:
    pass


@dataclass
class ModeChanged:
    silent: bool
    vision: bool


@dataclass
class UserTranscript:
    text: str
    final: bool = True


@dataclass
class MicLevel:
    level: float
    elapsed: float = 0.0


@dataclass
class TurnRecap:
    timings: dict = field(default_factory=dict)


Event = Any
