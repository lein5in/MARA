import copy
import itertools
import threading
from types import SimpleNamespace

_ids = itertools.count(1)


def reply(*texts, stop_reason="end_turn"):
    return {"texts": list(texts), "tools": [], "stop_reason": stop_reason}


def tool_call(name, args=None, *texts, more=None, stop_reason="tool_use"):
    tools = [(name, args or {})] + list(more or [])
    return {"texts": list(texts), "tools": tools, "stop_reason": stop_reason}


def fail(exc, *texts_before):
    return {"texts": list(texts_before), "error": exc}


def hang(*texts_before):
    return {"texts": list(texts_before), "tools": [], "stop_reason": "end_turn", "hang": True}


class FakeStream:
    def __init__(self, spec):
        self.spec = spec
        self.closed = threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        self.closed.set()

    def __iter__(self):
        for t in self.spec["texts"]:
            yield SimpleNamespace(type="text", text=t)
        for _ in self.spec.get("tools", []):
            yield SimpleNamespace(type="input_json", partial_json="{}")
        if self.spec.get("hang"):
            self.closed.wait(10)
            raise ConnectionError("stream closed")
        if "error" in self.spec:
            raise self.spec["error"]

    @property
    def text_stream(self):
        for t in self.spec["texts"]:
            yield t
        if "error" in self.spec:
            raise self.spec["error"]

    def get_final_message(self):
        content = []
        text = "".join(self.spec["texts"])
        if text:
            content.append(SimpleNamespace(type="text", text=text))
        for name, args in self.spec["tools"]:
            content.append(SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=args))
        return SimpleNamespace(content=content, stop_reason=self.spec["stop_reason"],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.create_calls = []

    def stream(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if not self.script:
            raise AssertionError("fake client script exhausted")
        return FakeStream(self.script.pop(0))

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="en")])


class FakeAnthropic:
    def __init__(self, script):
        self.messages = FakeMessages(script)

    def push(self, *specs):
        self.messages.script.extend(specs)


class FakeMemory:
    def __init__(self):
        self.data = {"facts": [], "preferences": [], "context": []}
        self.pause = None

    def get_context_for_prompt(self):
        return ""

    def items(self):
        return {k: list(v) for k, v in self.data.items()}

    def add_fact(self, f):
        self.data["facts"].append(f)

    def add_preference(self, f):
        self.data["preferences"].append(f)

    def add_context(self, f):
        self.data["context"].append(f)

    def remove_last_fact(self):
        return self.data["facts"].pop() if self.data["facts"] else None

    def remove_matching(self, text):
        removed = [f for f in self.data["facts"] if text in f]
        self.data["facts"] = [f for f in self.data["facts"] if text not in f]
        return removed

    def clear(self):
        self.data = {"facts": [], "preferences": [], "context": []}

    def set_pause(self, iso):
        self.pause = iso

    def get_pause(self):
        return self.pause

    def clear_pause(self):
        self.pause = None
