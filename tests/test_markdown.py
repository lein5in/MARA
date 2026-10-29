from core.text import split_fences, code_lines, copyable_code


def test_plain_text_is_one_segment():
    assert split_fences("Hello there.") == [{"kind": "text", "text": "Hello there."}]


def test_fenced_code_and_text():
    raw = "The loop is off by one.\n```python fix\n def f(x):\n-    return x - 1\n+    return x\n```\nThat's it."
    segs = split_fences(raw)
    assert [s["kind"] for s in segs] == ["text", "code", "text"]
    code = segs[1]
    assert code["lang"] == "python" and code["diff"] and code["closed"]
    assert segs[2]["text"] == "That's it."


def test_streaming_unclosed_fence():
    segs = split_fences("Look:\n```js\nconst a = 1;")
    assert segs[-1] == {"kind": "code", "lang": "js", "diff": False, "code": "const a = 1;", "closed": False}


def test_diff_line_numbers_match_reference():
    code = " def average(items):\n     total = 0\n-    for i in range(1, len(items)):\n+    for i in range(len(items)):\n         total += items[i]"
    rows = code_lines(code, True)
    assert [(n, m) for n, m, _ in rows] == [(1, " "), (2, " "), (3, "-"), (3, "+"), (4, " ")]
    assert rows[3][2] == "    for i in range(len(items)):"
    assert "range(1," not in copyable_code(code, True)


def test_non_diff_keeps_minus_lines():
    rows = code_lines("x = 1\n-y", False)
    assert rows == [(1, " ", "x = 1"), (2, " ", "-y")]
