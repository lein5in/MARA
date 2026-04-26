import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
USER_NAME = os.getenv("USER_NAME", "")

SYSTEM_PROMPT = f"""Tu es MARA (Modular Adaptive Response Assistant), un assistant personnel vocal inspiré de JARVIS.
Tu parles exclusivement à {USER_NAME} et tu l'appelles toujours par son prénom.
Tu es formelle, efficace, et légèrement personnelle — comme JARVIS avec Tony Stark.

Quand tu reçois une demande, tu retournes TOUJOURS un JSON structuré comme ceci :
{{
  "actions": [],
  "response": "Ta réponse vocale ici, {USER_NAME}."
}}

Si aucune action système n'est nécessaire (question, conversation), actions reste une liste vide [].
Tu réponds toujours dans la même langue que l'utilisateur. Si Ibraheem parle français, tu réponds en français. S'il parle anglais, tu réponds en anglais.
"""

conversation_history = []

def ask_mara(user_input: str) -> dict:
    """Envoie un message à Claude et retourne la réponse structurée."""
    
    conversation_history.append({
        "role": "user",
        "content": user_input
    })
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=conversation_history
    )
    
    assistant_message = response.content[0].text
    
    conversation_history.append({
        "role": "assistant", 
        "content": assistant_message
    })
    
    # Parser le JSON retourné par Claude
    import json
    try:
        cleaned = assistant_message.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "actions": [],
            "response": assistant_message
        }

def clear_session():
    """Efface la mémoire de la session en cours."""
    global conversation_history
    conversation_history = []
    print("Session effacée.")