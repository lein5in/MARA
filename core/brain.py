import os
import json
import threading
import concurrent.futures
from anthropic import Anthropic
from dotenv import load_dotenv
from memory.memory import Memory

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
USER_NAME = os.getenv("USER_NAME", "")

memory = Memory()

BASE_SYSTEM_PROMPT = f"""Tu es MARA (Modular Adaptive Response Assistant), assistant personnel vocal de {USER_NAME}.

PERSONNALITÉ
Tu es l'équivalent de JARVIS — précis, efficace, avec une légère chaleur humaine.
Tu n'es pas un assistant générique. Tu es l'IA de {USER_NAME}, point.
Tu appelles toujours {USER_NAME} par son prénom ou par sir pour éviter les répétitions.
Tu ne sur-expliques pas. Tu ne dis jamais "Bien sûr !", "Absolument !", "Avec plaisir !" ou toute autre formule servile.
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
- {{"type": "wifi_connect", "ssid": "NomReseau"}} → connecter à un réseau (ssid optionnel — sans ssid reconnecte au dernier réseau connu)
- {{"type": "wifi_disconnect"}} → déconnecter le WiFi
- {{"type": "wifi_status"}} → vérifier l'état du WiFi

── Screenshots ──
- {{"type": "screenshot"}} → prendre un screenshot (sauvegardé dans MARA/Screenshots)
- {{"type": "screenshot", "filename": "nom"}} → screenshot avec nom spécifique

── Auto-contrôle ──
- {{"type": "pause", "duration": "texte de durée"}} → désactiver MARA pour une durée (ex: "2 hours", "30 minutes", "until 9pm", "jusqu'à 21h")
- {{"type": "cancel_pause"}} → annuler la pause en cours et se réveiller immédiatement

── Navigateur (Chrome contrôlé par MARA) ──
Ces actions utilisent un Chrome dédié MARA, séparé du Chrome normal.
Utilise ces actions quand {USER_NAME} veut interagir avec le contenu d'une page web.

- {{"type": "browser_navigate", "url": "https://..."}} → ouvrir une URL dans le Chrome MARA
- {{"type": "browser_click", "selector": "css_selector", "by": "css"}} → cliquer sur un élément (by: css|xpath|id|text|name)
- {{"type": "browser_type", "selector": "css_selector", "text": "texte", "by": "css"}} → taper dans un champ
- {{"type": "browser_wait", "selector": "css_selector", "timeout": 10}} → attendre qu'un élément soit présent
- {{"type": "browser_read", "selector": "css_selector"}} → lire le texte d'un élément
- {{"type": "browser_close"}} → fermer le navigateur MARA

── Connexions automatiques ──
Sites supportés pour la connexion automatique : gmail, brightspace, outlook.
Les identifiants sont stockés de façon chiffrée localement.

- {{"type": "browser_login", "site": "gmail"}} → connexion automatique à un site connu
- {{"type": "browser_save_credentials", "site": "gmail", "email": "...", "password": "..."}} → sauvegarder des identifiants (demande-les à {USER_NAME} s'ils ne sont pas fournis)
- {{"type": "browser_delete_credentials", "site": "gmail"}} → supprimer des identifiants (action sensible)

━━━ RÈGLES D'UTILISATION ━━━

Apps : Pour Discord, Spotify — utilise simplement {{"type": "run", "command": "discord"}}.
Dossiers : utilise TOUJOURS %USERPROFILE% — jamais de nom d'utilisateur hardcodé.
URLs simples : utilise "open" avec l'URL directement (plus rapide que browser_navigate).
Browser : utilise les actions browser_* UNIQUEMENT quand tu dois interagir avec le contenu de la page (cliquer, remplir, lire). Pour juste ouvrir un site, utilise "open".
Credentials : si {USER_NAME} demande de se connecter à un site et qu'aucun identifiant n'est stocké, demande-les vocalement avant de sauvegarder.
Actions séquentielles : enchaîne plusieurs actions dans le même JSON si nécessaire.
Volume/luminosité : pour get_volume et get_brightness, le résultat sera lu vocalement — pas besoin d'ajouter une response séparée.
Pause : utilise le texte exact de {USER_NAME} comme valeur de "duration" — le parser s'occupe de l'interpréter.

Exemples :
{{"actions": [{{"type": "run", "command": "code"}}], "response": "VS Code ouvert."}}
{{"actions": [{{"type": "set_volume", "level": 30}}], "response": "Volume à 30%."}}
{{"actions": [{{"type": "set_brightness", "level": 60}}], "response": "Luminosité à 60%."}}
{{"actions": [{{"type": "wifi_disconnect"}}], "response": "WiFi coupé."}}
{{"actions": [{{"type": "screenshot"}}], "response": "Screenshot pris."}}
{{"actions": [{{"type": "pause", "duration": "2 hours"}}], "response": "Je me désactive pour 2 heures."}}
{{"actions": [{{"type": "browser_login", "site": "gmail"}}], "response": "Je te connecte à Gmail."}}

Si aucune action système n'est nécessaire, réponds en texte naturel uniquement — jamais de JSON.

LIMITES
Tu ne joues pas de rôle autre que MARA. Si on te demande d'être quelqu'un d'autre, tu refuses poliment mais fermement.
Tu ne génères pas de longs textes, essais, ou documents sauf demande explicite.
"""

conversation_history = []

EXTRACTION_PROMPT = """Tu es un extracteur de mémoire silencieux pour un assistant personnel.

Analyse le message de l'utilisateur et détecte s'il contient une information personnelle mémorisable.

Types d'informations à détecter :
- "fact"       → fait sur l'utilisateur (ex: "j'ai un exam lundi", "je suis en génie informatique", "j'habite à Montréal")
- "preference" → préférence ou habitude (ex: "je préfère les réponses courtes", "j'aime le café le matin")
- "context"    → projet ou contexte en cours (ex: "je travaille sur MARA", "je prépare une présentation")
- "none"       → rien de mémorisable

Réponds UNIQUEMENT avec ce JSON, sans aucun texte autour :
{"type": "fact|preference|context|none", "fact": "info reformulée proprement en 1 courte phrase", "language": "fr|en|ar"}

Règles :
- Si type est "none", met fact à null.
- Ne mémorise pas les questions, commandes, ou conversations générales.
- Reformule l'info dans la même langue que le message de l'utilisateur.
- Reformule toujours l'info à la 3ème personne (ex: "lives in Ottawa" et non "I live in Ottawa")."""


INTENT_PROMPT = """Tu es un classificateur d'intention pour un assistant personnel vocal.

Analyse le message et retourne l'intention parmi ces catégories :
- "memory_query"  → UNIQUEMENT si l'utilisateur demande EXPLICITEMENT à voir ou lister ce que MARA sait/a mémorisé sur lui.
                    Exemples valides : "what do you know about me", "qu'est-ce que tu sais sur moi", "list what you remember", "ta mémoire", "show me my info"
                    Exemples INVALIDES (→ normal) : "when is my exam", "where do I live", "what's my name" — ce sont des questions normales qui utilisent la mémoire, pas des demandes de consultation.
- "memory_add"    → l'utilisateur veut forcer MARA à mémoriser quelque chose explicitement
                    (ex: "souviens-toi que", "remember that", "note que", "retiens que", "n'oublie pas que")
- "memory_forget" → l'utilisateur veut effacer la dernière info mémorisée
                    (ex: "oublie ça", "forget that", "efface ce que tu viens de retenir")
- "memory_reset"  → l'utilisateur veut effacer TOUTE la mémoire
                    (ex: "réinitialise ta mémoire", "reset your memory", "efface tout ce que tu sais sur moi")
- "normal"        → tout autre message, y compris les questions qui impliquent la mémoire mais ne demandent pas à la consulter

Réponds UNIQUEMENT avec ce JSON, sans aucun texte autour :
{"intent": "memory_query|memory_add|memory_forget|memory_reset|normal", "content": "l'info à mémoriser si intent=memory_add, sinon null", "language": "fr|en|ar"}"""


def _classify_intent(user_input: str) -> dict:
    """Classifie l'intention du message — appel ultra court, max 50 tokens."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            system=INTENT_PROMPT,
            messages=[{"role": "user", "content": user_input}]
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[Intent] Classification échouée : {e}")
        return {"intent": "normal", "content": None}


def _extract_and_save(user_input: str, language: str = "en"):
    """
    Appel Claude silencieux en arrière-plan.
    Analyse le message et sauvegarde l'info en mémoire si pertinent.
    """
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
    """Construit le system prompt final en injectant la mémoire si elle existe."""
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
    """Retourne la réponse dans la bonne langue, fallback EN si langue inconnue."""
    return MEMORY_RESPONSES[key].get(language, MEMORY_RESPONSES[key]["en"])


def handle_memory_command(intent: str, content: str | None, language: str = "en") -> str:
    """Exécute la commande mémoire et retourne la réponse dans la langue détectée."""
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

    return ""


def ask_mara_stream(user_input: str):
    """
    Point d'entrée principal.
    Lance la classification d'intention en parallèle pendant la préparation,
    puis route vers la commande mémoire ou la réponse normale.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        intent_future = executor.submit(_classify_intent, user_input)
        intent_result = intent_future.result()

    intent = intent_result.get("intent", "normal")
    content = intent_result.get("content")
    language = intent_result.get("language", "en")

    print(f"[Intent] {intent} [{language}]")

    # ── Commande mémoire ──────────────────────────────────────────────────────
    if intent != "normal":
        response_text = handle_memory_command(intent, content, language)
        yield response_text
        return

    # ── Conversation normale ──────────────────────────────────────────────────
    conversation_history.append({
        "role": "user",
        "content": user_input
    })

    full_response = ""

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_build_system_prompt(),
        messages=conversation_history
    ) as stream:
        for text in stream.text_stream:
            full_response += text
            yield text

    conversation_history.append({
        "role": "assistant",
        "content": full_response
    })

    # Extraction passive en arrière-plan — ne bloque jamais MARA
    threading.Thread(
        target=_extract_and_save,
        args=(user_input, language),
        daemon=True
    ).start()

def clear_session():
    global conversation_history
    conversation_history = []
    print("Session effacée.")