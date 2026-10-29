# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

MARA is a voice-driven personal assistant for Windows (PyQt5 UI, local Whisper STT, Claude for reasoning, Fish Audio TTS). Python 3.11, a `venv/` in the repo root. Tests live in `tests/` (pytest, all fakes, no network/GPU).

## Commands

```
venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py          # the app
python -m core.cli      # console frontend, same agent, no Qt/voice
pytest -q
```

Required `.env` keys (gitignored): `ANTHROPIC_API_KEY`, `FISH_API_KEY`, `USER_NAME`. Whisper runs on CUDA (PyTorch). The push-to-talk trigger is the `f13` key (`TRIGGER_KEY` in `core/config.py`), bound to a mouse button. User data (`mara.key`, `*.enc`, `app_registry.json`, `profile.md`) lives in `%APPDATA%\MARA` (`DATA_DIR` in `core/config.py`), seeded from the old in-repo copies at startup. Tests set `MARA_DATA_DIR` to a temp folder so they never touch real data.

## Architecture

Flow of one turn:

```
listener (F13 + Whisper) ─┐
typed text (window) ──────┴─> Session.submit ──> Session.run_turn ──> Agent.run_turn
                                   │ (yes/no while a confirmation is pending)        │
                                   └──> ConfirmationBroker <── ConfirmationRequested ─┤
Agent loop: stream Sonnet ─ TextDelta ─> Session ─> SpeechStream (TTS) + emit ─> UI  │
            tool_use ─> Registry.execute(name, args, ctx) ─> tool_result ─> call again (cap MAX_TOOL_ITERATIONS)
```

- `core/brain.py`: `Agent` owns `history` (real `text`/`tool_use`/`tool_result` blocks, trimmed by whole turns), streams with the Anthropic SDK, runs tools, and closes a turn cleanly on API errors or cancel (no orphan `tool_use`). `ConfirmationBroker` holds one `Future` per pending confirmation. Haiku runs in the background for memory extraction.
- `core/events.py`: typed events (`TextDelta`, `ToolStarted`, `ToolFinished`, `ConfirmationRequested`, `StateChanged`, `Visual`, `Error`, `Done`, UI-control events). They are the only contract between the core and any frontend.
- `core/tools/`: `registry.py` (`Tool` = schema + handler + risk `read`/`local`/`confirm`; `execute` times calls and turns exceptions into error results). One module per area: `system_tools`, `app_tools`, `browser_tools`, `memory_tools`, `ui_tools`. A handler is `fn(ctx, **args)` returning a string (or `ToolResult`); raise `ToolError` for an expected failure. To add a tool: register it in the right module; nothing else to wire.
- `core/session.py`: Qt-free orchestrator (input queue, pause and wake word, quit after the goodbye is spoken, speech per turn). `core/cli.py` and the Qt worker both drive it.
- `core/ui/`: `theme.py` (color tokens, fonts from `assets/fonts`, the single QSS builder, icons, HTML snippets), `window.py` (`MainWindow`: header, thread, composer, tray; `on_event` is the only entry point), `messages.py` (user/mara blocks, receipts, streaming reply with code blocks, confirmation card), `composer.py`, `visual.py` (offline web view), `worker.py` (`MARAWorker`, a `QThread` running `Session` and re-emitting every event through one `sig_event = pyqtSignal(object)`). `main.py` wires worker, window, visual window and orb. `core/orb.py` is the 3D orb; `core/shutdown.py` closes Chrome on exit.
- `core/listener.py` publishes `StateChanged(LISTENING)`, `MicLevel` and partial `UserTranscript` through `set_event_hook`.
- `core/system.py` (OS calls, silent/vision flags, pause state), `core/browser.py` (Selenium Chrome, isolated profile), `core/app_registry.py`, `core/text.py` (pure text helpers: `clean_text`, sentence splitting, yes/no parsing).

**Memory** (`memory/`): `Memory` is a Singleton storing Fernet-encrypted JSON (facts and preferences, surfaced into the system prompt by `Agent.system_prompt`); `credentials.py` is a separate encrypted store for browser logins. The prompt tells the model to use memory implicitly and never recite it.

## Conventions

- Replies are spoken: the prompt asks for plain text, 1-2 sentences, in the user's language (EN/FR/AR). Tool results are English for the model; user-facing fixed strings that MARA says herself are localized like `OFFLINE` in `core/session.py`. UI strings are English.
- `BASE_SYSTEM_PROMPT` is an f-string: literal braces must be doubled (`{{ }}`).

## Rules

- Windows-only app. Never touch, move or delete memory/*.enc, memory/mara.key, .env.
- Do not write comments or docstrings unless the code is genuinely non-obvious.
- Do not change contracts between modules (function signatures, events, return formats) without telling the user first and listing every caller affected.
- Visual changes: QSS lives in one place, no logic and no threading changes in styling tasks.
- All cross-thread UI updates go through pyqtSignal.
- Prefer small diffs. Do not reformat files you are not editing.
- After any edit, run `python -m compileall core memory main.py`, `ruff check . --isolated --select E4,E7,E9,F --exclude venv` and `pytest -q`, and report errors.
- Never add a dependency without asking.
- Do not commit; the user commits.
