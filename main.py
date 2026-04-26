from core.brain import ask_mara, clear_session
from core.listener import listen

print("MARA initialisée.")
print("Maintiens ENTRÉE pour parler, relâche pour envoyer.\n")

while True:
    user_input = listen()

    if not user_input:
        print("Je n'ai rien entendu, réessaie.")
        continue

    if "quit" in user_input.lower():
        print("MARA désactivée.")
        break

    result = ask_mara(user_input)
    print(f"MARA : {result['response']}")

    if result['actions']:
        print(f"Actions : {result['actions']}")