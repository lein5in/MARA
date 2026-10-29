import sys

from core.brain import Agent, ConfirmationBroker
from core.events import (
    TextDelta, ToolStarted, ToolFinished, ConfirmationRequested, Visual, Error, Done,
    QuitRequested, ShowInterface, HideInterface, ConversationReset, ModeChanged,
)

DIM, ACCENT, WARN, RESET = "\033[2m", "\033[38;2;232;160;180m", "\033[38;2;229;181;103m", "\033[0m"


class Console:
    def __init__(self, out=sys.stdout, ask=input):
        self.out = out
        self.ask = ask
        self.broker = ConfirmationBroker()
        self.quit = False

    def write(self, text: str):
        self.out.write(text)
        self.out.flush()

    def handle(self, event):
        if isinstance(event, TextDelta):
            self.write(event.text)
        elif isinstance(event, ToolStarted):
            self.write(f"\n{DIM}  … {event.name} {event.args}{RESET}")
        elif isinstance(event, ToolFinished):
            mark = f"{ACCENT}✓{RESET}" if event.ok else f"{WARN}✗{RESET}"
            self.write(f"\r{mark} {event.name} {DIM}{event.duration:.1f}s {event.summary}{RESET}\n")
        elif isinstance(event, ConfirmationRequested):
            self.write(f"\n{WARN}! {event.title}{RESET}: {event.description}\n  {event.tool} {event.args}\n")
            answer = self.ask("  confirm? [y/N] ").strip().lower()
            self.broker.resolve(answer in ("y", "yes", "o", "oui"), event.id)
        elif isinstance(event, Visual):
            self.write(f"\n{DIM}[visual: {event.title}, {len(event.html)} chars of HTML]{RESET}\n")
        elif isinstance(event, Error):
            self.write(f"\n{WARN}error: {event.message}{RESET}\n")
        elif isinstance(event, QuitRequested):
            self.quit = True
        elif isinstance(event, (ShowInterface, HideInterface, ConversationReset, ModeChanged)):
            self.write(f"\n{DIM}[{type(event).__name__}]{RESET}\n")
        elif isinstance(event, Done):
            self.write("\n")


def main():
    console = Console()
    agent = Agent(emit=console.handle, broker=console.broker)
    print("MARA console. Type a message, /reset to clear the conversation, /quit to exit.")
    while not console.quit:
        try:
            text = input(f"{ACCENT}› {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/reset":
            agent.reset()
            print(f"{DIM}conversation cleared{RESET}")
            continue
        sys.stdout.write(f"{ACCENT}mara{RESET} ")
        agent.run_turn(text, source="typed")


if __name__ == "__main__":
    main()
