from core.brain import ask_mara, clear_session

print("MARA initialisée. Tape 'quit' pour quitter.\n")

while True:
    user_input = input("Toi : ")
    
    if user_input.lower() == "quit":
        break
    
    if user_input.lower() == "clear":
        clear_session()
        continue
        
    result = ask_mara(user_input)
    print(f"MARA : {result['response']}")
    
    if result['actions']:
        print(f"Actions : {result['actions']}")