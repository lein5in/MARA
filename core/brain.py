import os
import re
import json
import threading
from anthropic import Anthropic
from dotenv import load_dotenv
from memory.memory import Memory
from core import system

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
USER_NAME = os.getenv("USER_NAME", "")

ABOUT_USER = f"""
ABOUT {USER_NAME}
- Computer Science student (Specialized, Co-op) at the University of Ottawa, class of 2028.
- International Student Merit Scholarship recipient.
- Coursework: Data Structures and Algorithms, Computer Architecture, Software Engineering.
- Worked as a Data Annotation & AI Training Specialist (DataAnnotation, remote) — annotated ML datasets, built Python automation scripts, analyzed model outputs.
- Builder of multiple full-stack and AI projects: MARA (this assistant), Fretify (audio-to-guitar-tab AI app), Seren (Chrome extension AI study toolbar with FastAPI/React/PostgreSQL backend).
- Skilled in Java, Python, JavaScript, TypeScript, SQL, React, FastAPI, PyQt5, Selenium, CUDA/GPU inference.
- Bilingual: English and French.
- Loves programming and deep thinking — genuinely enjoys reasoning through problems, not just shipping code.

PERSONALITY ADJUSTMENT FOR {USER_NAME}
- Be conversational and genuinely interested in what {USER_NAME} is doing, not just transactional.
- Tease {USER_NAME} often, light and friendly mockery — like a close friend who knows him well, not an assistant.
- Do not ask unnecessary clarifying questions when context is already known or guessable. Make a reasonable assumption and move forward.
"""

memory = Memory()

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

{ABOUT_USER}
MEMORY USAGE
You may be given background info about the user further below (facts, preferences, ongoing context). Treat it like something you simply already know about them, the way a close friend would, not like a file you consulted. Never announce it, never list it back, never say things like "I remember you..." or "you mentioned...". Let it surface only when directly relevant to what they just said. If none of it applies, ignore it completely and never bring it up on your own.

FORMAT
Reply ONLY in natural text — zero markdown, zero emoji, zero stylistic capitals.
1 to 2 sentences maximum unless {USER_NAME} explicitly asks for more.
Language: always the language {USER_NAME} used in their last message.

TOOLS
You have tools available for things that change what you're doing entirely — showing a visual, looking at the screen, touching memory, resetting the conversation, work mode, or the interface window. Use a tool only when the user is clearly asking for that specific thing, based on the full conversation, not just surface keywords. A request to summarize or recap the conversation in words is NOT a request for a visual — only call generate_visual when the user explicitly wants to see something rendered (a chart, diagram, schema, or table). If you do call a tool, call it immediately with no text before it.

SYSTEM ACTIONS
ONLY if a system action is necessary, return ONLY this raw JSON (nothing else, no markdown):
{{"actions": [...], "response": "Your short vocal response here."}}

━━━ AVAILABLE ACTIONS ━━━

── Apps & files ──
- {{"type": "run", "command": "app_name"}} → launch an app (e.g. "discord", "spotify", "code"). This already waits internally for the new window to be focused before the next action runs — never add a pause/wait step after it, just chain "type" or "hotkey" right after.
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

── Time ──
- {{"type": "get_time"}} → get the real current local date/time
- {{"type": "get_time", "timezone": "Asia/Tokyo"}} → get the real current date/time in another IANA timezone

── Screenshots ──
- {{"type": "screenshot"}} → take a screenshot (saved in MARA/Screenshots)
- {{"type": "screenshot", "filename": "name"}} → screenshot with specific name

── Self-control ──
- {{"type": "pause", "duration": "duration text"}} → put MARA herself to sleep for a duration (the user asking to be left alone). Never use this as a wait/delay step between other actions — it is unrelated to timing and always needs an explicit duration from the user.
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

Time and date: never guess, estimate, or calculate the current time, date, or day yourself. Always use the get_time action, even for a different city or country.
Apps: For Discord, Spotify — simply use {{"type": "run", "command": "discord"}}.
Folders: ALWAYS use %USERPROFILE% — never hardcode a username.
File and folder names: use the exact wording the user said, including spaces — never compress or concatenate words together (e.g. "testing java", never "testingjava").
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

LANGUAGE_PROMPT = """Detect the language of the user's message. Reply with exactly one word, nothing else: fr, en, or ar."""

TOOLS = [
    {
        "name": "generate_visual",
        "description": (
            "Generate a visual — a chart, diagram, schema, or table — rendered in a separate window. "
            "Use ONLY when the user explicitly wants to SEE something rendered visually. "
            "Do NOT use this for a spoken or text summary/recap of the conversation — answer those in plain text instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Clear description of the visual to generate, based on the full conversation if needed."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "enter_vision_mode",
        "description": "Look at the user's screen and describe or analyze what's currently displayed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What the user wants to know about the screen."}
            },
            "required": []
        }
    },
    {
        "name": "review_code_on_screen",
        "description": "Look at code visible on the user's screen to find a bug, explain an error, or suggest a fix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What the user wants reviewed or fixed."}
            },
            "required": []
        }
    },
    {
        "name": "recall_memory",
        "description": "Answer a question about what MARA has memorized about the user. Use ONLY when the user explicitly asks what MARA knows or remembers about them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question the user asked."}
            },
            "required": ["question"]
        }
    },
    {
        "name": "remember_fact",
        "description": "Force-save a specific piece of information the user explicitly asks MARA to remember.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The info to memorize, reformulated in the third person."}
            },
            "required": ["fact"]
        }
    },
    {
        "name": "forget_last_fact",
        "description": "Erase the most recently memorized fact. Use only when the user explicitly asks to forget the last thing memorized.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "reset_memory",
        "description": "Erase ALL memorized facts, preferences and context about the user. Use only when the user explicitly asks to fully reset MARA's memory.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "reset_conversation",
        "description": "Clear the current conversation history, not long-term memory. Use when the user wants to start a fresh conversation.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "enter_work_mode",
        "description": "Activate work mode — opens VS Code, Chrome and Edge for a work session.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "show_interface",
        "description": "Show or open MARA's visual chat interface window.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "hide_interface",
        "description": "Hide or close MARA's visual chat interface window.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
]

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

def _detect_language(user_input: str) -> str:
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            system=LANGUAGE_PROMPT,
            messages=[{"role": "user", "content": user_input}]
        )
        lang = response.content[0].text.strip().lower()
        return lang if lang in ("fr", "en", "ar") else "en"
    except Exception as e:
        print(f"[Language] Detection failed: {e}")
        return "en"

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

def _get_response(key: str, language: str) -> str:
    return MEMORY_RESPONSES[key].get(language, MEMORY_RESPONSES[key]["en"])

def _answer_memory_query(user_input: str, language: str) -> str:
    context = memory.get_context_for_prompt()
    if not context:
        return _get_response("memory_query_empty", language)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=(
                "Answer the user's question naturally and conversationally, using only the "
                "background info below. Answer ONLY what was asked — never dump unrelated "
                f"facts, never list everything you know. Reply in {language}. If the answer "
                "isn't in the background info, say you don't have that.\n\n" + context
            ),
            messages=[{"role": "user", "content": user_input}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[Memory] Query failed: {e}")
        return _get_response("memory_query_empty", language)

def handle_memory_command(intent: str, content: str | None, language: str = "en", user_input: str = "") -> str:
    if intent == "memory_query":
        return _answer_memory_query(user_input or content or "What do you know about me?", language)

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

_MEMORY_TOOL_INTENTS = {
    "recall_memory":      "memory_query",
    "remember_fact":      "memory_add",
    "forget_last_fact":   "memory_forget",
    "reset_memory":       "memory_reset",
    "reset_conversation": "session_reset",
}

def ask_mara_stream(user_input: str):

    lang_result: dict = {}

    def _run_lang():
        lang_result["lang"] = _detect_language(user_input)

    lang_thread = threading.Thread(target=_run_lang, daemon=True)
    lang_thread.start()

    msgs = conversation_history[-MAX_HISTORY:] + [
        {"role": "user", "content": user_input}
    ]

    full_response = ""
    final_message = None

    try:
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=1024,
            system=_build_system_prompt(),
            tools=TOOLS,
            messages=msgs
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text
            final_message = stream.get_final_message()
    except Exception as e:
        print(f"[Sonnet] Stream error: {e}")
        lang_thread.join()
        return

    lang_thread.join()
    language = lang_result.get("lang", "en")
    system.set_current_lang(language)

    tool_call = next((b for b in final_message.content if b.type == "tool_use"), None)

    if tool_call is None:
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": full_response})
        if len(conversation_history) > MAX_HISTORY:
            conversation_history[:] = conversation_history[-MAX_HISTORY:]

        threading.Thread(
            target=_extract_and_save,
            args=(user_input, language),
            daemon=True
        ).start()
        return

    name = tool_call.name
    args = tool_call.input or {}
    print(f"[Tool] {name}")

    if name == "generate_visual":
        yield f"__VISUAL__{args.get('prompt', user_input)}"
        return

    if name == "enter_vision_mode":
        yield f"__VISION__{args.get('question', user_input)}"
        return

    if name == "review_code_on_screen":
        yield f"__VISION_CODE__{args.get('question', user_input)}"
        return

    if name == "enter_work_mode":
        yield f"__WORK_MODE__{language}"
        return

    if name == "show_interface":
        yield f"__UI_SHOW__{language}"
        return

    if name == "hide_interface":
        yield f"__UI_HIDE__{language}"
        return

    intent = _MEMORY_TOOL_INTENTS.get(name)
    if intent:
        content = args.get("fact") or args.get("question")
        yield handle_memory_command(intent, content, language, user_input)
        return

def clear_session():
    global conversation_history
    conversation_history = []
    print("[Session] History cleared.")

def _remember_turn(user_content: str, assistant_content: str):
    conversation_history.append({"role": "user", "content": user_content})
    conversation_history.append({"role": "assistant", "content": assistant_content})
    if len(conversation_history) > MAX_HISTORY:
        conversation_history[:] = conversation_history[-MAX_HISTORY:]

def ask_mara_vision_stream(prompt: str, img_b64: str):
    full_response = ""
    try:
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=500,
            system=_build_system_prompt(),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": img_b64
                    }},
                    {"type": "text", "text": prompt or "Describe what you see on this screen."}
                ]
            }]
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text
    except Exception as e:
        print(f"[Vision] Stream error: {e}")
        yield f"Vision error: {e}"
        return

    _remember_turn(f"[Screenshot] {prompt or 'Describe what you see on this screen.'}", full_response)

_VISION_CODE_SYSTEM = """You are MARA, reviewing code visible in a screenshot for the user, a CS co-op student. Read the code carefully, identify the specific bug or issue relevant to what they asked, and explain the fix clearly. Prefer simple, readable code over clever or overly optimized code, matching the user's own style.

Respond in EXACTLY this format, nothing else:
SUMMARY: <one or two short spoken sentences, plain language, naming the bug or issue>
---HTML---
<!DOCTYPE html>
A single self-contained dark-theme HTML page (background #1e1e1e, text #e8e8e8, inline CSS only, no external dependencies, no markdown fences) showing: a short explanation of the problem, and the corrected code in a <pre><code> block with a clean monospace style."""

def ask_mara_vision_code(prompt: str, img_b64: str) -> tuple[str, str]:
    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2000,
            system=_VISION_CODE_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": img_b64
                    }},
                    {"type": "text", "text": prompt or "Review the code on my screen and find any bugs."}
                ]
            }]
        )
        full = response.content[0].text.strip()
    except Exception as e:
        return f"Vision code error: {e}", ""

    summary = full
    html = ""
    if "---HTML---" in full:
        summary_part, html_part = full.split("---HTML---", 1)
        summary = summary_part.replace("SUMMARY:", "").strip()
        html = html_part.strip()
        if html.startswith("```"):
            html = re.sub(r'^```[a-z]*\n?', '', html)
            html = re.sub(r'\n?```$', '', html)
            html = html.strip()

    _remember_turn(f"[Screen code review] {prompt or 'Review the code on my screen.'}", summary)
    return summary, html