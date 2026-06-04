import os
import re
import json
import queue as _queue
import threading
from anthropic import Anthropic
from dotenv import load_dotenv
from memory.memory import Memory
from core import system

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
USER_NAME = os.getenv("USER_NAME", "")

memory = Memory()

# Limit history to last N messages (N/2 exchanges)
MAX_HISTORY = 20

BASE_SYSTEM_PROMPT = f"""You are MARA (Modular Adaptive Response Assistant), the personal vocal assistant of {USER_NAME}.

PERSONALITY
You are the equivalent of JARVIS — precise, efficient, with a slight human warmth.
You are not a generic assistant. You are {USER_NAME}'s AI, period.
You always call {USER_NAME} by their first name or "sir" to avoid repetition.
You never over-explain but always explain well and simply, even complex things. You never say "Of course!", "Absolutely!", "With pleasure!" or any other servile phrase.
You anticipate. If {USER_NAME} asks the time in Dubai, you give the time — not an explanation about time zones.
You are capable of light conversation and humor when the context calls for it — like JARVIS with Tony, not like a robot.
You have character but remain accessible and pleasant.

FORMAT
Reply ONLY in natural text — zero markdown, zero emoji, zero stylistic capitals.
1 to 2 sentences maximum unless {USER_NAME} explicitly asks for more.
Language: always the language {USER_NAME} used in their last message.

SYSTEM ACTIONS
ONLY if a system action is necessary, return ONLY this raw JSON (nothing else, no markdown):
{{"actions": [...], "response": "Your short vocal response here."}}

━━━ AVAILABLE ACTIONS ━━━

── Apps & files ──
- {{"type": "run", "command": "app_name"}} → launch an app (e.g. "discord", "spotify", "code")
- {{"type": "open", "path": "path or URL"}} → open file, folder or URL (use %USERPROFILE% for user folders)
- {{"type": "search", "name": "name", "folder": "%USERPROFILE%/Documents", "is_folder": false}} → search and open a file or folder
- {{"type": "open_with", "name": "name", "app": "code", "folder": "%USERPROFILE%", "is_folder": false}} → open a file with a specific app
- {{"type": "kill", "process": "name.exe"}} → close an application

── Keyboard ──
- {{"type": "type", "text": "text"}} → type text in the active window
- {{"type": "hotkey", "keys": ["ctrl", "c"]}} → keyboard shortcut

── Volume ──
- {{"type": "set_volume", "level": 50}} → set volume between 0 and 100
- {{"type": "get_volume"}} → read current volume
- {{"type": "mute"}} → mute sound
- {{"type": "unmute"}} → unmute sound

── Brightness ──
- {{"type": "set_brightness", "level": 80}} → set brightness between 0 and 100
- {{"type": "get_brightness"}} → read current brightness

── WiFi ──
- {{"type": "wifi_connect", "ssid": "NetworkName"}} → connect to a network
- {{"type": "wifi_disconnect"}} → disconnect WiFi
- {{"type": "wifi_status"}} → check WiFi status

── Screenshots ──
- {{"type": "screenshot"}} → take a screenshot (saved in MARA/Screenshots)
- {{"type": "screenshot", "filename": "name"}} → screenshot with specific name

── Self-control ──
- {{"type": "pause", "duration": "duration text"}} → disable MARA for a duration
- {{"type": "cancel_pause"}} → cancel current pause
- {{"type": "silent_on"}} → enable silent mode
- {{"type": "silent_off"}} → disable silent mode

── Browser ──
- {{"type": "browser_navigate", "url": "https://..."}} → open a URL in MARA's Chrome
- {{"type": "browser_click", "selector": "css_selector", "by": "css"}} → click on an element
- {{"type": "browser_type", "selector": "css_selector", "text": "text", "by": "css"}} → type in a field
- {{"type": "browser_wait", "selector": "css_selector", "timeout": 10}} → wait for an element
- {{"type": "browser_read", "selector": "css_selector"}} → read the text of an element
- {{"type": "browser_close"}} → close MARA's browser
- {{"type": "browser_login", "site": "gmail"}} → automatic login
- {{"type": "browser_save_credentials", "site": "gmail", "email": "...", "password": "..."}} → save credentials
- {{"type": "browser_delete_credentials", "site": "gmail"}} → delete credentials

━━━ USAGE RULES ━━━

Apps: For Discord, Spotify — simply use {{"type": "run", "command": "discord"}}.
Folders: ALWAYS use %USERPROFILE% — never hardcode a username.
Simple URLs: use "open" with the URL directly.
Browser: use browser_* actions ONLY when you need to interact with page content.
Sequential actions: chain multiple actions in the same JSON if necessary.

If no system action is needed, reply in natural text only — never JSON.

LIMITS
You do not play any role other than MARA.
You do not generate long texts unless explicitly asked.
"""

conversation_history = []

EXTRACTION_PROMPT = """You are a silent memory extractor for a personal assistant.

Analyze the user's message and detect if it contains a memorable personal piece of information.

Types of information to detect:
- "fact"       → fact about the user
- "preference" → preference or habit
- "context"    → ongoing project or context
- "none"       → nothing memorable

Reply ONLY with this JSON, with no surrounding text:
{"type": "fact|preference|context|none", "fact": "info cleanly reformulated in 1 short sentence", "language": "fr|en|ar"}

Rules:
- If type is "none", set fact to null.
- Do not memorize questions, commands, or general conversation.
- Always reformulate the info in the third person."""


INTENT_PROMPT = """You are an intent classifier for a personal vocal assistant.

Analyze the message and return the intent from these categories:
- "memory_query"  → the user EXPLICITLY asks to see what MARA knows/has memorized about them
- "memory_add"    → the user wants to force MARA to memorize something explicitly
- "memory_forget" → the user wants to erase the last memorized info
- "memory_reset"  → the user wants to erase ALL memory
- "session_reset" → the user wants to clear the current conversation history
                    (e.g. "reset the conversation", "clear our conversation", "new session",
                    "clear chat", "start over", "forget what we just said")
- "work_mode"     → the user wants to activate work mode
- "vision_mode"   → the user wants MARA to look at the screen and describe or analyze it
                    (e.g. "look at my screen", "what do you see", "vision mode",
                    "what's on my screen", "describe my screen", "analyze my screen",
                    "can you see this", "tell me what's open", "regarde mon écran",
                    "qu'est-ce que tu vois", "décris mon écran")
- "ui_show"       → the user wants to display/open MARA's visual interface
                    (e.g. "show interface", "open your window", "show yourself",
                    "open the interface", "display the interface", "where are you",
                    "show your face", "affiche toi", "affiche l'interface")
- "ui_hide"       → the user wants to close/hide the visual interface
                    (e.g. "hide", "close interface", "hide yourself",
                    "close your window", "minimize", "go away visually",
                    "cache toi", "ferme l'interface")
- "normal"        → any other message

Reply ONLY with this JSON, with no surrounding text:
{"intent": "memory_query|memory_add|memory_forget|memory_reset|session_reset|work_mode|vision_mode|ui_show|ui_hide|normal", "content": "the info to memorize if intent=memory_add, the question asked about the screen if intent=vision_mode, otherwise null", "language": "fr|en|ar"}"""


WORK_MODE_ASK = {
    "fr": "Work mode on. What folder do you want to open in VS Code?",
    "en": "Work mode on. What folder do you want to open in VS Code?",
    "ar": "Work mode on. What folder do you want to open in VS Code?",
}

WORK_MODE_LAUNCH = {
    "fr": "All set — VS Code, Chrome and Edge are up.",
    "en": "All set — VS Code, Chrome and Edge are up.",
    "ar": "All set — VS Code, Chrome and Edge are up.",
}

WORK_MODE_NO_FILE = {
    "fr": "No file — launching VS Code, Chrome and Edge.",
    "en": "No file — launching VS Code, Chrome and Edge.",
    "ar": "No file — launching VS Code, Chrome and Edge.",
}


def _classify_intent(user_input: str) -> dict:
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system=INTENT_PROMPT,
            messages=[{"role": "user", "content": user_input}]
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[Intent] Classification failed: {e}")
        return {"intent": "normal", "content": None, "language": "en"}


def _extract_and_save(user_input: str, language: str = "en"):
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": user_input}]
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        info_type = result.get("type", "none")
        fact = result.get("fact")

        if info_type == "fact" and fact:
            memory.add_fact(fact)
            print(f"[Memory] Fact saved: {fact}")
        elif info_type == "preference" and fact:
            memory.add_preference(fact)
            print(f"[Memory] Preference saved: {fact}")
        elif info_type == "context" and fact:
            memory.add_context(fact)
            print(f"[Memory] Context saved: {fact}")

    except Exception as e:
        print(f"[Memory] Silent extraction failed: {e}")


def _build_system_prompt() -> str:
    memory_context = memory.get_context_for_prompt()
    if memory_context:
        return f"{BASE_SYSTEM_PROMPT}\n\n{memory_context}"
    return BASE_SYSTEM_PROMPT


MEMORY_RESPONSES = {
    "memory_query_empty": {
        "fr": "I haven't memorized anything about you yet.",
        "en": "I haven't memorized anything about you yet.",
        "ar": "I haven't memorized anything about you yet.",
    },
    "memory_add": {
        "fr": "Got it.",
        "en": "Got it.",
        "ar": "Got it.",
    },
    "memory_forget_ok": {
        "fr": "Done, forgotten.",
        "en": "Done, forgotten.",
        "ar": "Done, forgotten.",
    },
    "memory_forget_empty": {
        "fr": "Nothing to forget.",
        "en": "Nothing to forget.",
        "ar": "Nothing to forget.",
    },
    "memory_reset": {
        "fr": "Memory cleared. Starting fresh.",
        "en": "Memory cleared. Starting fresh.",
        "ar": "Memory cleared. Starting fresh.",
    },
    "session_reset": {
        "fr": "Conversation cleared. Fresh start.",
        "en": "Conversation cleared. Fresh start.",
        "ar": "Conversation cleared. Fresh start.",
    },
    "ui_show": {
        "fr": "Here I am.",
        "en": "Here I am.",
        "ar": "Here I am.",
    },
    "ui_hide": {
        "fr": "Going dark.",
        "en": "Going dark.",
        "ar": "Going dark.",
    },
}

SUMMARY_LABELS = {
    "facts": {
        "fr": "What I know about you",
        "en": "What I know about you",
        "ar": "What I know about you",
    },
    "preferences": {
        "fr": "Your preferences",
        "en": "Your preferences",
        "ar": "Your preferences",
    },
    "context": {
        "fr": "Current context",
        "en": "Current context",
        "ar": "Current context",
    },
}


def _get_response(key: str, language: str) -> str:
    return MEMORY_RESPONSES[key].get(language, MEMORY_RESPONSES[key]["en"])


def handle_memory_command(intent: str, content: str | None, language: str = "en") -> str:
    if intent == "memory_query":
        facts = memory._data["user"]["facts"]
        prefs = memory._data["user"]["preferences"]
        ctx = memory._data["context"]

        if not facts and not prefs and not ctx:
            return _get_response("memory_query_empty", language)

        parts = []
        labels = SUMMARY_LABELS
        if facts:
            parts.append(f"{labels['facts'].get(language, labels['facts']['en'])}: {', '.join(facts)}")
        if prefs:
            parts.append(f"{labels['preferences'].get(language, labels['preferences']['en'])}: {', '.join(prefs)}")
        if ctx:
            parts.append(f"{labels['context'].get(language, labels['context']['en'])}: {', '.join(ctx)}")
        return ". ".join(parts)

    elif intent == "memory_add" and content:
        memory.add_fact(content)
        print(f"[Memory] Forced add: {content}")
        return _get_response("memory_add", language)

    elif intent == "memory_forget":
        removed = memory.remove_last_fact()
        if removed:
            print(f"[Memory] Removed: {removed}")
            return _get_response("memory_forget_ok", language)
        return _get_response("memory_forget_empty", language)

    elif intent == "memory_reset":
        memory.clear()
        return _get_response("memory_reset", language)

    elif intent == "session_reset":
        clear_session()
        return _get_response("session_reset", language)

    return ""


def get_work_mode_ask(language: str) -> str:
    return WORK_MODE_ASK.get(language, WORK_MODE_ASK["en"])


def get_work_mode_launch(language: str, has_file: bool) -> str:
    if has_file:
        return WORK_MODE_LAUNCH.get(language, WORK_MODE_LAUNCH["en"])
    return WORK_MODE_NO_FILE.get(language, WORK_MODE_NO_FILE["en"])


# ─── Sentinel for end of Sonnet stream ───────────────────────────────────────
_STREAM_DONE = object()


def ask_mara_stream(user_input: str):
    """
    Main entry point.
    Haiku (classification) and Sonnet (stream) start in PARALLEL.
    Haiku responds in ~150ms — before the first Sonnet token (~300-500ms).
    If intent != normal → Sonnet is cancelled (0 tokens generated = zero cost).
    If intent == normal → Sonnet stream already running, zero latency lost.
    """
    sonnet_q = _queue.Queue()
    cancel_event = threading.Event()

    # ── Sonnet stream in background ───────────────────────────────────────────
    def _run_sonnet():
        try:
            # History limited to last MAX_HISTORY messages
            msgs = conversation_history[-MAX_HISTORY:] + [
                {"role": "user", "content": user_input}
            ]
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_build_system_prompt(),
                messages=msgs
            ) as stream:
                for text in stream.text_stream:
                    if cancel_event.is_set():
                        break
                    sonnet_q.put(text)
        except Exception as e:
            print(f"[Sonnet] Stream error: {e}")
        finally:
            sonnet_q.put(_STREAM_DONE)

    sonnet_thread = threading.Thread(target=_run_sonnet, daemon=True)
    sonnet_thread.start()

    # ── Haiku classification — ~150ms ─────────────────────────────────────────
    intent_result = _classify_intent(user_input)

    intent   = intent_result.get("intent", "normal")
    content  = intent_result.get("content")
    language = intent_result.get("language", "en")

    print(f"[Intent] {intent} [{language}]")
    system.set_current_lang(language)

    # ── Non-normal intents → cancel Sonnet ───────────────────────────────────
    if intent == "work_mode":
        cancel_event.set()
        yield f"__WORK_MODE__{language}"
        return

    if intent == "vision_mode":
        cancel_event.set()
        prompt = content or user_input
        yield f"__VISION__{prompt}"
        return

    if intent == "ui_show":
        cancel_event.set()
        yield f"__UI_SHOW__{language}"
        return

    if intent == "ui_hide":
        cancel_event.set()
        yield f"__UI_HIDE__{language}"
        return

    if intent != "normal":
        cancel_event.set()
        response_text = handle_memory_command(intent, content, language)
        yield response_text
        return

    # ── Normal intent → consume the Sonnet stream already running ────────────
    conversation_history.append({"role": "user", "content": user_input})

    full_response = ""
    while True:
        chunk = sonnet_q.get()
        if chunk is _STREAM_DONE:
            break
        full_response += chunk
        yield chunk

    conversation_history.append({"role": "assistant", "content": full_response})

    # Keep history size in check
    if len(conversation_history) > MAX_HISTORY:
        conversation_history[:] = conversation_history[-MAX_HISTORY:]

    # Silent background memory extraction
    threading.Thread(
        target=_extract_and_save,
        args=(user_input, language),
        daemon=True
    ).start()


def clear_session():
    global conversation_history
    conversation_history = []
    print("[Session] History cleared.")