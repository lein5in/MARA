import queue
import threading

from core import system, metrics
from core.brain import Agent, ConfirmationBroker
from core.config import TRIGGER_KEY
from core.events import (
    TextDelta, ToolStarted, StateChanged, State, QuitRequested, TurnStarted, ConfirmationRequested, Error, Notice,
)
from core.text import parse_yes_no, has_word
from core.log import get_logger
log = get_logger(__name__)

WAKE_WORD = "mara"

OFFLINE = {
    "fr": f"Je suis en pause. Maintiens {TRIGGER_KEY.upper()} et dis mon nom pour me réveiller.",
    "en": f"I'm paused. Hold {TRIGGER_KEY.upper()} and say my name to wake me.",
    "ar": f"أنا في وضع الإيقاف المؤقت. اضغط {TRIGGER_KEY.upper()} وقل اسمي لإيقاظي.",
}
BACK = {"fr": "Je suis de retour.", "en": "I'm back.", "ar": "لقد عدت."}
CONFIRM_HINT = {
    "fr": "Dis oui ou annule.",
    "en": "Say yes or cancel.",
    "ar": "قل نعم أو إلغاء.",
}


def localized(table: dict, lang: str | None = None) -> str:
    return table.get(lang or system.current_lang(), table["en"])


class NullSpeech:
    def feed(self, text):
        pass

    def end(self, timeout=None):
        pass

    def cancel(self):
        pass


def _default_speech():
    from core.voice import make_speech
    return make_speech()


def _default_say(text: str):
    from core.voice import speak
    speak(text)


class Session:
    def __init__(self, emit, agent: Agent | None = None, listen_fn=None, speech_factory=None, say_fn=None,
                 memory=None):
        self.emit = emit
        self.broker = ConfirmationBroker()
        self.agent = agent or Agent(emit=self._on_agent_event, broker=self.broker, memory=memory)
        if agent is not None:
            agent.emit = self._on_agent_event
            agent.broker = self.broker
        self.memory = self.agent.memory
        self.listen_fn = listen_fn
        self.speech_factory = speech_factory or _default_speech
        self.say_fn = say_fn or _default_say
        self.inputs: queue.Queue = queue.Queue()
        self.running = True
        self._speech = NullSpeech()
        self._speaking = False
        self._quit_pending = False
        self._was_paused = False
        self.busy = False
        self._barged = False

    def submit(self, text: str, source: str = "typed") -> bool:
        text = (text or "").strip()
        if not text:
            return False
        if self.broker.pending_id():
            answer = parse_yes_no(text)
            if answer is None:
                self.emit(Error(localized(CONFIRM_HINT)))
                return False
            self.broker.resolve(answer)
            return True
        self.inputs.put((text, source))
        return True

    def resolve_confirmation(self, accepted: bool, cid: str | None = None) -> bool:
        return self.broker.resolve(accepted, cid)

    def new_conversation(self):
        if self.busy:
            self.agent.request_reset()
        else:
            self.agent.reset()

    def stop(self):
        self.running = False
        self.broker.cancel_all()
        self.agent.cancel()
        self._speech.cancel()

    def barge_in(self):
        if not self.busy and isinstance(self._speech, NullSpeech):
            return False
        log.info("[Session] Barge-in: stopping speech and the current request.")
        self._barged = True
        self._speech.cancel()
        if self.busy:
            self.agent.cancel()
        return True

    def _on_agent_event(self, event):
        if isinstance(event, QuitRequested):
            self._quit_pending = True
            return
        if isinstance(event, TextDelta):
            metrics.mark("first_token")
            self._speech.feed(event.text)
            if not self._speaking and not system.is_silent():
                self._speaking = True
                self.emit(StateChanged(State.SPEAKING))
        elif isinstance(event, (ToolStarted, ConfirmationRequested)) and self._speaking:
            self._speaking = False
        self.emit(event)

    def _voice_loop(self):
        while self.running:
            try:
                text = self.listen_fn()
            except Exception:
                log.exception("[Session] listener failed")
                continue
            if text and self.running:
                self.submit(text, "voice")

    def start_listening(self):
        if self.listen_fn:
            threading.Thread(target=self._voice_loop, daemon=True, name="mara-voice").start()

    def run_turn(self, text: str, source: str):
        if source != "voice" or not metrics.active():
            metrics.start(source)
        self.emit(TurnStarted(text, source))
        self._speaking = False
        self._barged = False
        self._speech = NullSpeech() if system.is_silent() else self.speech_factory()
        self.busy = True
        try:
            self.agent.run_turn(text, source)
        finally:
            self.busy = False
            self._speech.end()
            self._speech = NullSpeech()
            self._speaking = False
            metrics.finish()
        if self._quit_pending:
            self.running = False
            self.emit(QuitRequested())
            return
        if self._barged:
            self._barged = False
            return
        self.emit(StateChanged(State.PAUSED if system.is_paused(self.memory) else State.IDLE))

    def _say(self, text: str):
        self.emit(StateChanged(State.SPEAKING))
        try:
            self.say_fn(text)
        except Exception:
            log.exception("[Session] say failed")

    def _handle_paused(self, text: str, source: str = "typed"):
        self.emit(TurnStarted(text, source))
        if has_word(text, WAKE_WORD):
            system.cancel_pause(self.memory)
            self.emit(Notice(localized(BACK)))
            self._say(localized(BACK))
            self.emit(StateChanged(State.IDLE))
        else:
            self.emit(Notice(localized(OFFLINE)))
            self._say(localized(OFFLINE))
            self.emit(StateChanged(State.PAUSED))

    def step(self, timeout: float = 0.1) -> bool:
        paused = system.is_paused(self.memory)
        try:
            text, source = self.inputs.get(timeout=timeout)
        except queue.Empty:
            if not paused and self._was_paused:
                self.emit(StateChanged(State.IDLE))
            self._was_paused = paused
            return False
        self._was_paused = paused
        try:
            if paused:
                self._handle_paused(text, source)
            else:
                self.run_turn(text, source)
        except Exception:
            log.exception("[Session] turn crashed")
            self.emit(Error("Something went wrong in that turn. I'm still here."))
            self.emit(StateChanged(State.IDLE))
        return True

    def run(self):
        self.start_listening()
        self.emit(StateChanged(State.PAUSED if system.is_paused(self.memory) else State.IDLE))
        while self.running:
            self.step()
