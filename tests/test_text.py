import pytest

from core.text import clean_text, split_sentences, SentenceBuffer, pcm16_from_wav


@pytest.mark.parametrize("raw, expected", [
    ("Il est **dix-huit heures** à Paris.", "Il est dix-huit heures à Paris."),
    ("C’est l’heure de partir — vraiment.", "C’est l’heure de partir — vraiment."),
    ("الساعة الآن العاشرة صباحاً", "الساعة الآن العاشرة صباحاً"),
    ("The USA and the EU use AI daily.", "The USA and the EU use AI daily."),
    ("Run `pip install` now 🚀", "Run pip install now"),
    ("# Title\n- first\n- second", "Title first second"),
    ("See [the docs](https://example.com) here.", "See the docs here."),
    ("Here:\n```python\nprint(1)\n```\nDone.", "Here: Check the code on screen. Done."),
    ("well-known snake_case_name", "well-known snake_case_name"),
    ("Ça va ? Très bien !", "Ça va ? Très bien !"),
])
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Hello there. How are you?", ["Hello there.", "How are you?"]),
    ("Python 3.5 is old. Use 3.12!", ["Python 3.5 is old.", "Use 3.12!"]),
    ("Use a tool, e.g. a hammer. Then rest.", ["Use a tool, e.g. a hammer.", "Then rest."]),
    ("Install v1.2 first. Then v2.0.1 later.", ["Install v1.2 first.", "Then v2.0.1 later."]),
    ("Go to https://example.com/a.b?x=1 now. Done.", ["Go to https://example.com/a.b?x=1 now.", "Done."]),
    ("Quoi ? Vraiment ! Oui...", ["Quoi ?", "Vraiment !", "Oui..."]),
    ("He said \"stop.\" Then left.", ["He said \"stop.\"", "Then left."]),
    ("M. Dupont arrive. Il est là.", ["M. Dupont arrive.", "Il est là."]),
    ("مرحبا. كيف حالك؟ بخير", ["مرحبا.", "كيف حالك؟", "بخير"]),
    ("No punctuation at all", ["No punctuation at all"]),
])
def test_split_sentences(raw, expected):
    assert split_sentences(raw) == expected


def test_buffer_waits_for_decimal_and_keeps_punctuation():
    buf = SentenceBuffer()
    out = []
    for chunk in ["It costs 3", ".", "5 dollars", ". Really", "? Yes", "."]:
        out += buf.feed(chunk)
    out += buf.flush()
    assert out == ["It costs 3.5 dollars.", "Really?", "Yes."]


def test_buffer_does_not_cut_on_trailing_dot():
    buf = SentenceBuffer()
    assert buf.feed("Version v1.") == []
    assert buf.feed("2 is out. ") == []
    assert buf.feed("Next") == ["Version v1.2 is out."]
    assert buf.flush() == ["Next"]


def test_buffer_soft_split_needs_enough_words():
    buf = SentenceBuffer(soft_min_words=4)
    assert buf.feed("Oui, ") == []
    assert buf.feed("je pense que tu as raison, ") == []
    out = buf.feed("donc on y va")
    assert out == ["Oui, je pense que tu as raison,"]


def test_buffer_max_words():
    buf = SentenceBuffer(max_words=5)
    out = buf.feed("one two three four five six seven")
    assert out == ["one two three four five six"]
    assert buf.flush() == ["seven"]


def test_pcm16_from_wav_strips_header_and_odd_byte():
    wav = b"RIFF" + b"\x00" * 40 + b"\x01\x02\x03"
    assert pcm16_from_wav(wav) == b"\x01\x02"
    assert pcm16_from_wav(b"\x01\x02\x03\x04") == b"\x01\x02\x03\x04"
