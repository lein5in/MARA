# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

MARA is a voice-driven personal assistant for Windows (PyQt5 UI, local Whisper STT, Claude for reasoning, Fish Audio TTS). Python 3.11, a `venv/` in the repo root. There is no test suite, linter, or build step.

## Commands

```
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Required `.env` keys (gitignored): `ANTHROPIC_API_KEY`, `FISH_API_KEY`, `USER_NAME`. Whisper runs on CUDA (PyTorch). The push-to-talk trigger is the `f13` key (`TRIGGER_KEY` in `core/config.py`), bound to a mouse button. User data (`mara.key`, `*.enc`, `app_registry.json`, `profile.md`) lives in `%APPDATA%\MARA` (`DATA_DIR` in `core/config.py`), seeded from the old in-repo copies at startup; `launch_mara.bat/.vbs` and any legacy in-repo copies are machine-specific and gitignored.

## Architecture

Entry point `main.py` builds the Qt app, `MARAWindow` (chat UI), `MARAOrb` (3D orb), and a `MARAWorker` QThread, then wires the worker's `pyqtSignal`s to the window and orb. All cross-thread UI updates must go through those signals.

**Worker loop** (`MARAWorker.run` in `core/ui.py`): gets input from either the voice thread (`core/listener.py`, Whisper) or the text queue, calls `brain.ask_mara_stream`, and streams the reply sentence-by-sentence into TTS (`core/voice.py`) while emitting chunks to the UI.

**Routing in `core/brain.py`** is the central design: Sonnet (`claude-sonnet-5`) sees the full conversation and decides via native Anthropic tool-calling (`TOOLS`) whether to reply in plain text, call a capability tool, or emit a system-action JSON. Haiku only runs in parallel for language detection and background memory extraction. There are three result paths:
1. Plain text: streamed and appended to `conversation_history` (capped by `MAX_HISTORY`).
2. Tool call: `ask_mara_stream` yields a sentinel string (`__VISUAL__`, `__VISION__`, `__VISION_CODE__`, `__WORK_MODE__`, `__UI_SHOW__`, `__UI_HIDE__`), which the worker in `core/ui.py` checks on the first streamed chunk and dispatches. Memory tools are handled directly in `brain.py` via `handle_memory_command`. To add a tool, add it to `TOOLS`, handle it in `ask_mara_stream`, and add the sentinel handling in the worker loop.
3. System actions: the system prompt tells the model to return raw JSON `{"actions": [...], "response": "..."}`. The action types are documented in the prompt ("AVAILABLE ACTIONS") and implemented in `core/executor.py` (`execute`, with `_run`, `_open`, `_type`, `_search`, `browser_*`, and so on). Adding an action means updating both the prompt and the executor. `needs_confirmation` gates risky actions, and `READ_ACTIONS` in `ui.py` lists actions whose output is fed back as results.

Other modules: `core/system.py` (volume, brightness, WiFi, clock, screenshots, pause state, current language), `core/browser.py` (Selenium Chrome with an isolated profile under `%LOCALAPPDATA%\MARA`), `core/app_registry.py` (scans installed apps via PowerShell at startup), and vision mode (screenshot to Claude Vision, `ask_mara_vision_stream` / `ask_mara_vision_code`).

**Memory** (`memory/`): `Memory` is a Singleton storing Fernet-encrypted JSON (facts and preferences, surfaced into the system prompt by `_build_system_prompt`); `credentials.py` is a separate encrypted store for browser logins. The prompt tells the model to use memory implicitly and never recite it.

## Conventions

- The system prompt is an f-string, so literal JSON braces are doubled (`{{ }}`). Keep that when editing it.
- MARA's replies are spoken, so the prompt requires plain text with no markdown or emoji, 1-2 sentences, in the user's language (EN/FR/AR). Keep new user-facing strings localized the way `MEMORY_RESPONSES` is.

## Rules

- Windows-only app. Never touch, move or delete memory/*.enc, memory/mara.key, .env.
- Do not write comments or docstrings unless the code is genuinely non-obvious.
- Do not change contracts between modules (function signatures, signals, return formats) without telling the user first and listing every caller affected.
- Visual changes: QSS lives in one place, no logic and no threading changes in styling tasks.
- All cross-thread UI updates go through pyqtSignal.
- Prefer small diffs. Do not reformat files you are not editing.
- After any edit, run `python -m compileall core memory main.py` and report errors.
- Never add a dependency without asking.
- Do not commit; the user commits.

TODO: rewrite the Architecture section after the native-tools refactor.
