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
Button press → Whisper (local GPU) → Intent classification (Haiku)
                                              ↓
                              Claude Sonnet 4.6 streaming (parallel)
                                              ↓
                              Fish Audio TTS → real-time audio playback
                                              ↓
                              PyQt5 UI + 3D Neural Orb
```

**The key insight:** Haiku and Sonnet run in parallel. By the time Haiku classifies intent (~150ms), Sonnet has already started generating. This eliminates nearly all perceived latency.

---

## Features

**Voice & Speech**
- Push-to-talk trigger via a programmable mouse button (Logitech G502)
- Local speech recognition with OpenAI Whisper turbo on CUDA
- Real-time streaming TTS via Fish Audio S2 Pro
- Multilingual support — responds in the language you speak (EN/FR/AR)

**Intelligence**
- Powered by Claude Sonnet 4.6 for reasoning and conversation
- Claude Haiku for ultra-fast intent classification (~150ms)
- Parallel inference architecture — zero latency overhead
- Persistent encrypted memory (facts, preferences, context) across sessions
- Conversation history management with automatic summarization

**System Control**
- Launch and kill applications
- Control volume and screen brightness
- WiFi management
- Take screenshots
- Type text and trigger keyboard shortcuts in any window
- Self-pause with automatic wake-up timer

**Browser Automation**
- Dedicated Chrome instance with isolated profile
- Navigate, click, type, read page content
- Automatic credential management (encrypted)
- Combined with Vision mode for fully autonomous browser interaction

**Vision Mode**
- On command, MARA takes a screenshot and analyzes it with Claude Vision
- Can describe the screen, identify open apps, read content
- Can generate and execute browser actions based on what she sees
- Triggered vocally ("what do you see?") or via the UI button

**Interface**
- Floating terminal-style PyQt5 window (always on top, frameless)
- 3D neural orb — a transparent globe that pulses and glows based on state (listening / thinking / speaking)
- Silent mode — MARA acts without speaking
- Work mode — launches a full dev environment in one command

**Reliability**
- Boots automatically on Windows startup via Task Scheduler (silent, no terminal window)
- Whisper loads in the background — zero startup delay
- Encrypted local memory and credentials via Fernet
- Thread-safe architecture with Qt signals

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11.9 |
| Speech-to-Text | OpenAI Whisper turbo (CUDA, local) |
| LLM — Reasoning | Anthropic Claude Sonnet 4.6 (API) |
| LLM — Classification | Anthropic Claude Haiku (API) |
| Text-to-Speech | Fish Audio S2 Pro (streaming API) |
| UI Framework | PyQt5 |
| 3D Rendering | PyQt5 custom OpenGL-style widget |
| Browser Automation | Selenium + Chrome WebDriver |
| Audio I/O | sounddevice, scipy |
| Memory | Fernet-encrypted JSON (local) |
| GPU Acceleration | CUDA via PyTorch |
| OS Integration | Windows Task Scheduler, pycaw, subprocess |

---

## Project Structure

```
MARA/
├── main.py                 # Entry point — Qt app, worker thread, orb
├── core/
│   ├── listener.py         # Whisper STT + mouse button trigger
│   ├── brain.py            # Claude API + parallel inference + memory
│   ├── voice.py            # Fish Audio TTS + real-time PCM streaming
│   ├── executor.py         # System actions dispatcher
│   ├── browser.py          # Selenium Chrome automation
│   ├── app_registry.py     # Dynamic app registry via PowerShell
│   ├── system.py           # Volume, brightness, WiFi, screenshots
│   ├── ui.py               # PyQt5 floating window + worker thread
│   └── orb.py              # 3D neural orb widget
├── memory/
│   ├── memory.py           # Encrypted persistent memory (Singleton)
│   └── credentials.py      # Encrypted credential store
└── assets/
    └── app_registry.json
```

---

## Cost

MARA runs at approximately **$3.50–6.50/month** in API costs — less than a coffee.

| Service | Monthly Cost |
|---|---|
| Claude Sonnet 4.6 | ~$2–5 |
| Claude Haiku | ~$0.50 |
| Fish Audio S2 Pro | ~$1 |

Everything else runs locally at zero cost.

---

## What I learned building this

This project pushed me across a wide range of engineering challenges — real-time audio streaming, GPU inference, thread-safe Qt architecture, parallel API calls, encrypted local storage, browser automation, and Windows system integration. More than anything, it taught me how to architect a complex system where many moving parts need to work together reliably, without any single component blocking the others.

MARA is not a weekend project. It is an ongoing system I use every day and continue to improve.

---

*Built by Ibrahim — Ottawa, 2025–2026*