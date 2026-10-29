from core.events import ConversationReset
from core.tools.registry import Registry, ToolError, LOCAL, CONFIRM


def register(reg: Registry):
    @reg.tool("recall_memory",
              "List what MARA has memorized about the user. Use only when the user asks what you know or remember "
              "about them; answer only what they asked, in your own words.")
    def recall_memory(ctx):
        items = ctx.memory.items()
        lines = [f"{kind}: {entry}" for kind, entries in items.items() for entry in entries]
        return "\n".join(lines) if lines else "Nothing memorized yet."

    @reg.tool("remember", "Save something the user explicitly asks MARA to remember, rephrased in the third person.",
              {"fact": {"type": "string"},
               "kind": {"type": "string", "enum": ["fact", "preference", "context"]}},
              ["fact"], LOCAL, summarize=lambda a: a.get("fact", ""))
    def remember(ctx, fact, kind="fact"):
        if not fact or not fact.strip():
            raise ToolError("fact is empty")
        {"preference": ctx.memory.add_preference, "context": ctx.memory.add_context}.get(kind, ctx.memory.add_fact)(fact)
        return "Saved."

    @reg.tool("forget",
              "Forget memorized information. Pass a few words identifying what to forget; without them, forgets the "
              "most recent fact.",
              {"about": {"type": "string"}}, [], LOCAL, summarize=lambda a: a.get("about", "last fact"))
    def forget(ctx, about=None):
        if about:
            removed = ctx.memory.remove_matching(about)
            return f"Forgot {len(removed)} item(s)." if removed else f"Nothing memorized matches '{about}'."
        removed = ctx.memory.remove_last_fact()
        return "Forgot the last fact." if removed else "Nothing to forget."

    @reg.tool("reset_memory", "Erase ALL long-term memory about the user. Only on an explicit request.",
              risk=CONFIRM,
              confirm_text=lambda a: ("Erase all memory",
                                      "Deletes every fact, preference and context MARA has memorized about you. "
                                      "This cannot be undone."))
    def reset_memory(ctx):
        ctx.memory.clear()
        return "All memory erased."

    @reg.tool("reset_conversation",
              "Start a fresh conversation: clears the conversation history (not long-term memory).", risk=LOCAL)
    def reset_conversation(ctx):
        if ctx.agent is not None:
            ctx.agent.request_reset()
        ctx.emit(ConversationReset())
        return "Conversation history will be cleared after this reply. Confirm briefly."
