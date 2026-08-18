# MARA — Personal AI Assistant
### Modular Adaptive Response Assistant

> A fully local, voice-driven personal AI assistant inspired by JARVIS from Iron Man — built from scratch in Python, running 24/7 on a Windows laptop.

---

## What is MARA?

MARA is a personal AI assistant I designed and built over several months as a solo engineering project. The goal was simple: build something that actually feels like a real assistant — not a chatbot, not a demo, but a system that lives on your machine, knows who you are, and responds the moment you need it.

You press a button on your mouse, you talk, she answers — vocally, intelligently, and instantly.

---

## Architecture

MARA runs on a hybrid local/cloud architecture designed for speed, privacy, and low cost.

```
Button press → Whisper (local GPU) → Claude Sonnet 5, full context + native tools
                                              ↓
                         Sonnet decides: plain reply, system action,
                         or a tool call (visual, vision, memory, work mode...)
                                              ↓
                              Fish Audio TTS → real-time audio playback
                                              ↓
                              PyQt5 UI + 3D Neural Orb

               [in parallel] Haiku → language detection only (~150ms)
```

**The key insight:** routing is no longer guessed by a separate model reading your message in isolation. Sonnet — the model that already holds the full conversation — decides for itself, via native Anthropic tool-calling, whether to just reply, run a system action, or invoke a specific capability (generate a visual, look at the screen, touch memory, reset the conversation, etc). Haiku still runs in parallel, but only for lightweight language detection, so the perceived-latency gain is kept without the model ever misrouting a request based on a single out-of-context sentence.

---

## Features

**Voice & Speech**
- Push-to-talk trigger via a programmable mouse button (Logitech G502)
- Local speech recognition with OpenAI Whisper turbo on CUDA
- Real-time streaming TTS via Fish Audio S2 Pro, buffered by sentence for smoother delivery
- Multilingual support — responds in the language you speak (EN/FR/AR)

**Intelligence**
- Powered by Claude Sonnet 5 for reasoning, conversation, and self-directed tool use
- Native tool-calling for routing — Sonnet decides itself, with full conversation context, whether to answer normally or invoke a specific capability
- Claude Haiku for lightweight, parallel language detection and silent background memory extraction
- Persistent encrypted memory (facts, preferences, context) across sessions, surfaced naturally instead of recited
- Conversation history management with automatic trimming

**System Control**
- Launch and kill applications
- Control volume and screen brightness
- WiFi management
- Real local clock — no guessed times or dates
- Take screenshots
- Type text (clipboard-based, fast and accent-safe) and trigger keyboard shortcuts in any window
- Self-pause with automatic wake-up timer
- Indexed file search via the native Windows Search index, with disk-scan fallback

**Visual Output**
- On request, MARA generates a chart, diagram, or table and renders it in a dedicated window
- Built with Chart.js and inline SVG, dark-themed to match the rest of the interface
- Distinguishes an explicit request to *see* something from a plain spoken summary or recap

**Browser Automation**
- Dedicated Chrome instance with isolated profile
- Navigate, click, type, read page content
- Automatic credential management (encrypted)
- Combined with Vision mode for fully autonomous browser interaction

**Vision Mode**
- On command, MARA takes a screenshot and analyzes it with Claude Vision
- Can describe the screen, identify open apps, read content
- Dedicated code-review mode — reads code visible on screen, explains the bug, and opens a window with the corrected version
- Triggered vocally ("what do you see?", "look at my code") or via the UI

**Interface**
- Floating PyQt5 chat window — flat, minimal, deep charcoal theme, hairline borders, no gradients
- Message bubbles with avatars, pill-shaped input bar, Silent mode and Vision mode toggles
- 3D neural orb — a transparent globe that pulses and glows based on state (listening / thinking / speaking)
- Silent mode — MARA acts without speaking
- Work mode — launches a full dev environment in one command

**Reliability**
- Manual launch via `launch_mara.bat` / `launch_mara.vbs` — deliberate choice over silent auto-boot
- Whisper loads in the background — zero startup delay
- Encrypted local memory and credentials via Fernet
- Thread-safe architecture with Qt signals

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11.9 |
| Speech-to-Text | OpenAI Whisper turbo (CUDA, local) |
| LLM — Reasoning & routing | Anthropic Claude Sonnet 5 (API, native tool use) |
| LLM — Language detection & memory extraction | Anthropic Claude Haiku (API) |
| Text-to-Speech | Fish Audio S2 Pro (streaming API) |
| UI Framework | PyQt5 |
| 3D Rendering | PyQt5 custom OpenGL-style widget |
| Browser Automation | Selenium + Chrome WebDriver |
| Audio I/O | sounddevice, scipy |
| Memory | Fernet-encrypted JSON (local) |
| GPU Acceleration | CUDA via PyTorch |
| OS Integration | pycaw, screen_brightness_control, Windows Search index, subprocess |

---

## Project Structure

```
MARA/
├── main.py                 # Entry point — Qt app, worker thread, orb
├── core/
│   ├── listener.py         # Whisper STT + mouse button trigger
│   ├── brain.py            # Claude API + native tool-use routing + memory
│   ├── voice.py            # Fish Audio TTS + real-time PCM streaming
│   ├── executor.py         # System actions dispatcher
│   ├── browser.py          # Selenium Chrome automation
│   ├── app_registry.py     # Dynamic app registry via PowerShell
│   ├── system.py           # Volume, brightness, WiFi, clock, screenshots
│   ├── ui.py                # PyQt5 floating window + worker thread
│   └── orb.py               # 3D neural orb widget
├── memory/
│   ├── memory.py            # Encrypted persistent memory (Singleton)
│   └── credentials.py       # Encrypted credential store
└── assets/
    └── app_registry.json
```

---

## Cost

MARA runs at approximately **$3.50–7.50/month** in API costs — less than a coffee.

| Service | Monthly Cost |
|---|---|
| Claude Sonnet 5 | ~$2–6 |
| Claude Haiku | ~$0.50 |
| Fish Audio S2 Pro | ~$1 |

Everything else runs locally at zero cost.

---

## What I learned building this

This project pushed me across a wide range of engineering challenges — real-time audio streaming, GPU inference, thread-safe Qt architecture, native LLM tool-calling, encrypted local storage, browser automation, and Windows system integration. More than anything, it taught me how to architect a complex system where many moving parts need to work together reliably, without any single component blocking the others — and how to recognize when an architecture, not just a prompt, needs to change.

MARA is not a weekend project. It is an ongoing system I use every day and continue to improve.

---

*Built by Ibrahim — Ottawa, 2026*