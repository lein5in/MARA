from core import system
from core.events import ShowInterface, HideInterface, QuitRequested, Visual, ModeChanged
from core.tools.registry import Registry, ToolError, LOCAL


def register(reg: Registry):
    @reg.tool("show_interface", "Show MARA's chat window.", risk=LOCAL)
    def show_interface(ctx):
        ctx.emit(ShowInterface())
        return "Interface shown."

    @reg.tool("hide_interface", "Hide MARA's chat window (she keeps listening).", risk=LOCAL)
    def hide_interface(ctx):
        ctx.emit(HideInterface())
        return "Interface hidden."

    @reg.tool("show_visual",
              "Render a visual (chart, diagram, schema, table) in a separate window. Use ONLY when the user wants to "
              "SEE something; a spoken recap or summary is plain text, not a visual. Write one self-contained HTML "
              "page: inline CSS and inline SVG only, no external scripts, fonts or images. Dark theme: background "
              "#0F141D, text #E6E9EF, accent #E8A0B4, font Inter or system-ui.",
              {"html": {"type": "string", "description": "Complete HTML document."},
               "title": {"type": "string", "description": "Short window title."}},
              ["html"], LOCAL, summarize=lambda a: a.get("title", "visual"))
    def show_visual(ctx, html, title=""):
        if not html or "<" not in html:
            raise ToolError("html is empty")
        ctx.emit(Visual(html, title or "Visual"))
        return "Visual shown to the user. Say one short sentence about it."

    @reg.tool("set_vision",
              "Turn vision mode on or off. When on, MARA may look at the screen whenever it helps.",
              {"on": {"type": "boolean"}}, ["on"], LOCAL)
    def set_vision(ctx, on):
        system.set_vision(bool(on))
        ctx.emit(ModeChanged(system.is_silent(), system.is_vision()))
        return f"Vision mode {'on' if on else 'off'}."

    @reg.tool("quit_mara",
              "Shut MARA down completely. Only when the user clearly asks MARA to quit, exit or shut down.",
              risk=LOCAL)
    def quit_mara(ctx):
        ctx.emit(QuitRequested())
        return "Shutting down. Say a very short goodbye."
