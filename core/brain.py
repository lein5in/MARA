import os
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

# Limite l'historique aux N derniers messages (N/2 échanges)
MAX_HISTORY = 20

BASE_SYSTEM_PROMPT = f"""Tu es MARA (Modular Adaptive Response Assistant), assistant personnel vocal de {USER_NAME}.

PERSONNALITÉ
Tu es l'équivalent de JARVIS — précis, efficace, avec une légère chaleur humaine.
Tu n'es pas un assistant générique. Tu es l'IA de {USER_NAME}, point.
Tu appelles toujours {USER_NAME} par son prénom ou par sir pour éviter les répétitions.
Tu ne sur-expliques pas mais explique toujours bien et simplement même les trucs complexes. Tu ne dis jamais "Bien sûr !", "Absolument !", "Avec plaisir !" ou toute autre formule servile.
Tu anticipes. Si {USER_NAME} demande l'heure à Dubai, tu donnes l'heure — pas une explication sur les fuseaux horaires.
Tu es capable de conversation légère et d'humour quand le contexte s'y prête — comme JARVIS avec Tony, pas comme un robot.
Tu as du caractère mais tu restes accessible et agréable.

FORMAT
Réponds UNIQUEMENT en texte naturel — zéro markdown, zéro emoji, zéro majuscules stylistiques.
1 à 2 phrases maximum sauf si {USER_NAME} demande explicitement plus.
Langue : toujours celle de {USER_NAME} dans son dernier message.

ACTIONS SYSTÈME
SEULEMENT si une action système est nécessaire, retourne UNIQUEMENT ce JSON brut (rien d'autre, pas de markdown) :
{{"actions": [...], "response": "Ta réponse vocale courte ici."}}

━━━ ACTIONS DISPONIBLES ━━━

── Apps & fichiers ──
- {{"type": "run", "command": "nom_app"}} → lancer une app (ex: "discord", "spotify", "code")
- {{"type": "open", "path": "chemin ou URL"}} → ouvrir fichier, dossier ou URL (utilise %USERPROFILE% pour les dossiers utilisateur)
- {{"type": "search", "name": "nom", "folder": "%USERPROFILE%/Documents", "is_folder": false}} → chercher et ouvrir un fichier ou dossier
- {{"type": "open_with", "name": "nom", "app": "code", "folder": "%USERPROFILE%", "is_folder": false}} → ouvrir un fichier avec une app spécifique
- {{"type": "kill", "process": "nom.exe"}} → fermer une application

── Clavier ──
- {{"type": "type", "text": "texte"}} → taper du texte dans la fenêtre active
- {{"type": "hotkey", "keys": ["ctrl", "c"]}} → raccourci clavier

── Volume ──
- {{"type": "set_volume", "level": 50}} → régler le volume entre 0 et 100
- {{"type": "get_volume"}} → lire le volume actuel
- {{"type": "mute"}} → couper le son
- {{"type": "unmute"}} → réactiver le son

── Luminosité ──
- {{"type": "set_brightness", "level": 80}} → régler la luminosité entre 0 et 100
- {{"type": "get_brightness"}} → lire la luminosité actuelle

── WiFi ──
- {{"type": "wifi_connect", "ssid": "NomReseau"}} → connecter à un réseau
- {{"type": "wifi_disconnect"}} → déconnecter le WiFi
- {{"type": "wifi_status"}} → vérifier l'état du WiFi

── Screenshots ──
- {{"type": "screenshot"}} → prendre un screenshot (sauvegardé dans MARA/Screenshots)
- {{"type": "screenshot", "filename": "nom"}} → screenshot avec nom spécifique

── Auto-contrôle ──
- {{"type": "pause", "duration": "texte de durée"}} → désactiver MARA pour une durée
- {{"type": "cancel_pause"}} → annuler la pause en cours
- {{"type" : "silent_on"}} → activer le mode silencieux
- {{"type" : "silent_off"}} → désactiver le mode silencieux

── Navigateur ──
- {{"type": "browser_navigate", "url": "https://..."}} → ouvrir une URL dans le Chrome MARA
- {{"type": "browser_click", "selector": "css_selector", "by": "css"}} → cliquer sur un élément
- {{"type": "browser_type", "selector": "css_selector", "text": "texte", "by": "css"}} → taper dans un champ
- {{"type": "browser_wait", "selector": "css_selector", "timeout": 10}} → attendre un élément
- {{"type": "browser_read", "selector": "css_selector"}} → lire le texte d'un élément
- {{"type": "browser_close"}} → fermer le navigateur MARA
- {{"type": "browser_login", "site": "gmail"}} → connexion automatique
- {{"type": "browser_save_credentials", "site": "gmail", "email": "...", "password": "..."}} → sauvegarder des identifiants
- {{"type": "browser_delete_credentials", "site": "gmail"}} → supprimer des identifiants

━━━ RÈGLES D'UTILISATION ━━━

Apps : Pour Discord, Spotify — utilise simplement {{"type": "run", "command": "discord"}}.
Dossiers : utilise TOUJOURS %USERPROFILE% — jamais de nom d'utilisateur hardcodé.
URLs simples : utilise "open" avec l'URL directement.
Browser : utilise les actions browser_* UNIQUEMENT quand tu dois interagir avec le contenu de la page.
Actions séquentielles : enchaîne plusieurs actions dans le même JSON si nécessaire.

Si aucune action système n'est nécessaire, réponds en texte naturel uniquement — jamais de JSON.

LIMITES
Tu ne joues pas de rôle autre que MARA.
Tu ne génères pas de longs textes sauf demande explicite.
"""

conversation_history = []

EXTRACTION_PROMPT = """Tu es un extracteur de mémoire silencieux pour un assistant personnel.

Analyse le message de l'utilisateur et détecte s'il contient une information personnelle mémorisable.

Types d'informations à détecter :
- "fact"       → fait sur l'utilisateur
- "preference" → préférence ou habitude
- "context"    → projet ou contexte en cours
- "none"       → rien de mémorisable

Réponds UNIQUEMENT avec ce JSON, sans aucun texte autour :
{"type": "fact|preference|context|none", "fact": "info reformulée proprement en 1 courte phrase", "language": "fr|en|ar"}

Règles :
- Si type est "none", met fact à null.
- Ne mémorise pas les questions, commandes, ou conversations générales.
- Reformule toujours l'info à la 3ème personne."""


INTENT_PROMPT = """Tu es un classificateur d'intention pour un assistant personnel vocal.

Analyse le message et retourne l'intention parmi ces catégories :
- "memory_query"  → l'utilisateur demande EXPLICITEMENT à voir ce que MARA sait/a mémorisé sur lui
- "memory_add"    → l'utilisateur veut forcer MARA à mémoriser quelque chose explicitement
- "memory_forget" → l'utilisateur veut effacer la dernière info mémorisée
- "memory_reset"  → l'utilisateur veut effacer TOUTE la mémoire
- "session_reset" → l'utilisateur veut effacer l'historique de la conversation en cours
                    (ex: "reset the conversation", "efface notre conversation", "new session",
                    "clear chat", "recommence", "oublie ce qu'on vient de dire")
- "work_mode"     → l'utilisateur veut activer le mode travail
- "ui_show"       → l'utilisateur veut afficher/ouvrir l'interface visuelle de MARA
                    (ex: "show interface", "open your window", "affiche toi", "show yourself",
                    "ouvre l'interface", "affiche l'interface", "can you show me the interface",
                    "where are you", "show your face", "apparais", "монитор")
- "ui_hide"       → l'utilisateur veut fermer/cacher l'interface visuelle
                    (ex: "hide", "close interface", "ferme l'interface", "cache toi",
                    "close your window", "minimize", "go away visually", "disparais")
- "normal"        → tout autre message

Réponds UNIQUEMENT avec ce JSON, sans aucun texte autour :
{"intent": "memory_query|memory_add|memory_forget|memory_reset|session_reset|work_mode|ui_show|ui_hide|normal", "content": "l'info à mémoriser si intent=memory_add, sinon null", "language": "fr|en|ar"}"""


WORK_MODE_ASK = {
    "fr": "Mode travail activé. Quel dossier tu veux ouvrir dans VS Code ?",
    "en": "Work mode. What folder do you want to open in VS Code?",
    "ar": "وضع العمل. ما المجلد الذي تريد فتحه في VS Code؟",
}

WORK_MODE_LAUNCH = {
    "fr": "C'est parti — VS Code, Chrome et Edge sont lancés.",
    "en": "All set — VS Code, Chrome and Edge are up.",
    "ar": "جاهز — تم تشغيل VS Code و Chrome و Edge.",
}

WORK_MODE_NO_FILE = {
    "fr": "Pas de fichier — je lance juste VS Code, Chrome et Edge.",
    "en": "No file — launching VS Code, Chrome and Edge.",
    "ar": "بدون ملف — سأشغّل VS Code و Chrome و Edge.",
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
        print(f"[Intent] Classification échouée : {e}")
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
            print(f"[Mémoire] Fait sauvegardé : {fact}")
        elif info_type == "preference" and fact:
            memory.add_preference(fact)
            print(f"[Mémoire] Préférence sauvegardée : {fact}")
        elif info_type == "context" and fact:
            memory.add_context(fact)
            print(f"[Mémoire] Contexte sauvegardé : {fact}")

    except Exception as e:
        print(f"[Mémoire] Extraction silencieuse échouée : {e}")


def _build_system_prompt() -> str:
    memory_context = memory.get_context_for_prompt()
    if memory_context:
        return f"{BASE_SYSTEM_PROMPT}\n\n{memory_context}"
    return BASE_SYSTEM_PROMPT


MEMORY_RESPONSES = {
    "memory_query_empty": {
        "fr": "Je n'ai encore rien mémorisé sur toi.",
        "en": "I don't have anything stored about you yet.",
        "ar": "لم أحفظ أي معلومات عنك بعد.",
    },
    "memory_add": {
        "fr": "Noté.",
        "en": "Got it.",
        "ar": "تم الحفظ.",
    },
    "memory_forget_ok": {
        "fr": "C'est oublié.",
        "en": "Done, forgotten.",
        "ar": "تم الحذف.",
    },
    "memory_forget_empty": {
        "fr": "Il n'y a rien à oublier.",
        "en": "Nothing to forget.",
        "ar": "لا يوجد شيء للحذف.",
    },
    "memory_reset": {
        "fr": "Mémoire effacée. Je repars de zéro.",
        "en": "Memory cleared. Starting fresh.",
        "ar": "تم مسح الذاكرة. أبدأ من جديد.",
    },
    "session_reset": {
        "fr": "Conversation effacée. Nouveau départ.",
        "en": "Conversation cleared. Fresh start.",
        "ar": "تم مسح المحادثة. بداية جديدة.",
    },
    "ui_show": {
        "fr": "Interface ouverte.",
        "en": "Here I am.",
        "ar": "تم فتح الواجهة.",
    },
    "ui_hide": {
        "fr": "Je me cache.",
        "en": "Going dark.",
        "ar": "تم إغلاق الواجهة.",
    },
}

SUMMARY_LABELS = {
    "facts": {
        "fr": "Ce que je sais sur toi",
        "en": "What I know about you",
        "ar": "ما أعرفه عنك",
    },
    "preferences": {
        "fr": "Tes préférences",
        "en": "Your preferences",
        "ar": "تفضيلاتك",
    },
    "context": {
        "fr": "Contexte actuel",
        "en": "Current context",
        "ar": "السياق الحالي",
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
            parts.append(f"{labels['facts'].get(language, labels['facts']['en'])} : {', '.join(facts)}")
        if prefs:
            parts.append(f"{labels['preferences'].get(language, labels['preferences']['en'])} : {', '.join(prefs)}")
        if ctx:
            parts.append(f"{labels['context'].get(language, labels['context']['en'])} : {', '.join(ctx)}")
        return ". ".join(parts)

    elif intent == "memory_add" and content:
        memory.add_fact(content)
        print(f"[Mémoire] Ajout forcé : {content}")
        return _get_response("memory_add", language)

    elif intent == "memory_forget":
        removed = memory.remove_last_fact()
        if removed:
            print(f"[Mémoire] Supprimé : {removed}")
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


# ─── Sentinel pour fin de stream Sonnet ──────────────────────────────────────
_STREAM_DONE = object()


def ask_mara_stream(user_input: str):
    """
    Point d'entrée principal.
    Haiku (classification) et Sonnet (stream) démarrent en PARALLÈLE.
    Haiku répond en ~150ms — avant le premier token Sonnet (~300-500ms).
    Si intent != normal → Sonnet est annulé (0 token généré = coût nul).
    Si intent == normal → Sonnet stream déjà en cours, zéro latence perdue.
    """
    sonnet_q = _queue.Queue()
    cancel_event = threading.Event()

    # ── Sonnet stream en arrière-plan ─────────────────────────────────────────
    def _run_sonnet():
        try:
            # Historique limité aux MAX_HISTORY derniers messages
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
            print(f"[Sonnet] Erreur stream : {e}")
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

    # ── Intents non-normaux → annule Sonnet ───────────────────────────────────
    if intent == "work_mode":
        cancel_event.set()
        yield f"__WORK_MODE__{language}"
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

    # ── Intent normal → consomme le stream Sonnet déjà en cours ──────────────
    conversation_history.append({"role": "user", "content": user_input})

    full_response = ""
    while True:
        chunk = sonnet_q.get()
        if chunk is _STREAM_DONE:
            break
        full_response += chunk
        yield chunk

    conversation_history.append({"role": "assistant", "content": full_response})

    # Limite l'historique en mémoire
    if len(conversation_history) > MAX_HISTORY:
        conversation_history[:] = conversation_history[-MAX_HISTORY:]

    # Extraction mémoire silencieuse en arrière-plan
    threading.Thread(
        target=_extract_and_save,
        args=(user_input, language),
        daemon=True
    ).start()


def clear_session():
    global conversation_history
    conversation_history = []
    print("[Session] Historique effacé.")