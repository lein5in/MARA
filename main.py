import time
import json
import re
from core.brain import ask_mara_stream, clear_session
from core.listener import listen, start_emergency_listener
from core.voice import speak, speak_stream
from core.executor import execute, needs_confirmation
from core.app_registry import get_registry
from core import system
from memory.memory import Memory

# ─── Mémoire partagée ─────────────────────────────────────────────────────────
memory = Memory()

print("MARA initialisée.")
print("Scan des applications...")
get_registry()
print("Maintiens ENTRÉE pour parler, relâche pour envoyer.\n")

# Actions dont le résultat doit être lu vocalement par MARA
READ_RESULT_ACTIONS = {"browser_read", "get_volume", "get_brightness", "wifi_status"}


# ─── Callback réveil d'urgence ────────────────────────────────────────────────
def on_emergency_wake():
    """
    Appelé par le thread d'urgence quand "MARA" est dit 3x en moins de 8 secondes.
    Thread-safe — pas d'accès UI direct.
    """
    was_paused = system.is_paused(memory)
    system.cancel_pause(memory)
    if was_paused:
        print("[Emergency] MARA réveillée d'urgence.")
        speak("I'm here.")


# ─── Démarrage thread réveil d'urgence ───────────────────────────────────────
_emergency_stop = start_emergency_listener(on_emergency_wake)

while True:

    # ── Vérification pause ────────────────────────────────────────────────────
    if system.is_paused(memory):
        time.sleep(1)
        continue

    user_input = listen()

    if not user_input:
        print("Je n'ai rien entendu, réessaie.")
        continue

    if "quit" in user_input.lower():
        speak("À bientôt.")
        break

    # Accumule la réponse complète de Claude
    full_response = ""
    for chunk in ask_mara_stream(user_input):
        full_response += chunk

    # Tente de détecter un JSON avec actions
    actions = []
    vocal_response = full_response

    try:
        json_match = re.search(r'\{.*"actions"\s*:.*\}', full_response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if isinstance(result, dict) and "actions" in result:
                vocal_response = result.get("response", "")
                actions = result.get("actions", [])
        else:
            cleaned = full_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            result = json.loads(cleaned)
            if isinstance(result, dict) and "actions" in result:
                vocal_response = result.get("response", "")
                actions = result.get("actions", [])

    except (json.JSONDecodeError, AttributeError):
        pass

    # Joue la réponse vocale de MARA
    if vocal_response:
        speak_stream(iter([vocal_response]))

    print(f"MARA : {vocal_response or full_response}")

    # Exécution des actions
    if actions:
        if needs_confirmation(actions):
            speak("Cette action nécessite ta confirmation. Tu confirmes ?")
            confirmation = listen()
            if not any(word in confirmation.lower() for word in ["yes", "oui", "confirm", "go", "ok"]):
                speak("Action annulée.")
                continue

        results = execute(actions)
        print(f"[Executor] Résultats : {results}")

        # Résultats qui doivent être lus vocalement par MARA
        for action, result in zip(actions, results):
            action_type = action.get("type")

            # browser_read — reformulation naturelle via Claude
            if action_type == "browser_read" and result and not result.startswith("Erreur"):
                summary_prompt = f"Here is the content you just read from the browser. Summarize it naturally and briefly for the user, as you would speak it : {result}"
                summary_response = ""
                for chunk in ask_mara_stream(summary_prompt):
                    summary_response += chunk
                if summary_response:
                    speak_stream(iter([summary_response]))
                    print(f"MARA (lecture) : {summary_response}")

            # get_volume / get_brightness / wifi_status — lecture directe du résultat
            elif action_type in READ_RESULT_ACTIONS and result and not result.startswith("Erreur"):
                speak_stream(iter([result]))
                print(f"MARA ({action_type}) : {result}")

            # pause — MARA confirme puis entre en pause
            elif action_type == "pause" and result and not result.startswith("Erreur") and not result.startswith("Je n'ai pas"):
                speak_stream(iter([result]))
                print(f"MARA (pause) : {result}")