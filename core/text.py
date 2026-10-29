import re
import unicodedata

_DROP_CHARS = {"‍", "️", "︎"}

ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "cf", "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr",
    "approx", "fig", "p.ex", "mme", "mlle", "m",
}

_HARD = ".!?…؟"
_SOFT = ",;:،"
_CLOSERS = "\"'”’»)]"


def clean_text(text: str) -> str:
    text = re.sub(r"```.*?(```|$)", " Check the code on screen. ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*(?:[-•*]|\d+\.)\s+", "", text, flags=re.MULTILINE)
    text = "".join(
        c for c in text
        if c not in _DROP_CHARS and unicodedata.category(c) not in ("So", "Cs", "Co", "Cn")
    )
    return re.sub(r"\s+", " ", text).strip()


def _word_before(text: str, i: int) -> str:
    j = i
    while j > 0 and (text[j - 1].isalnum() or text[j - 1] == "."):
        j -= 1
    return text[j:i].lower().strip(".")


def _is_boundary(text: str, end: int, punct_start: int) -> bool:
    punct = text[punct_start:end]
    nxt = end
    while nxt < len(text) and text[nxt].isspace():
        nxt += 1
    next_char = text[nxt] if nxt < len(text) else ""
    if punct == ".":
        word = _word_before(text, punct_start)
        if word in ABBREVIATIONS:
            return False
        if len(word) == 1 and word.isalpha() and text[punct_start - 1].isupper():
            return False
        if next_char and next_char.islower():
            return False
    return True


def _scan(text: str, final: bool, soft_min_words: int = 0) -> list[int]:
    cuts = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        is_hard = c in _HARD
        is_soft = soft_min_words and c in _SOFT
        if not (is_hard or is_soft):
            i += 1
            continue
        punct_start = i
        while i < n and text[i] in (_HARD if is_hard else _SOFT):
            i += 1
        while i < n and text[i] in _CLOSERS:
            i += 1
        if i >= n:
            if final and is_hard:
                cuts.append(i)
            break
        if not text[i].isspace():
            continue
        if not final:
            k = i
            while k < n and text[k].isspace():
                k += 1
            if k >= n:
                break
        if is_soft and len(text[start:punct_start].split()) < soft_min_words:
            continue
        if is_hard and not _is_boundary(text, i, punct_start):
            continue
        cuts.append(i)
        start = i
    return cuts


def split_sentences(text: str) -> list[str]:
    cuts = _scan(text, final=True)
    parts = []
    prev = 0
    for cut in cuts:
        parts.append(text[prev:cut])
        prev = cut
    parts.append(text[prev:])
    return [p.strip() for p in parts if p.strip()]


class SentenceBuffer:
    def __init__(self, soft_min_words: int = 0, max_words: int = 40):
        self._buf = ""
        self._soft = soft_min_words
        self._max_words = max_words

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        out = []
        cuts = _scan(self._buf, final=False, soft_min_words=self._soft)
        if cuts:
            prev = 0
            for cut in cuts:
                piece = self._buf[prev:cut].strip()
                if piece:
                    out.append(piece)
                prev = cut
            self._buf = self._buf[prev:]
        if self._max_words and len(self._buf.split()) > self._max_words:
            head, _, tail = self._buf.rstrip().rpartition(" ")
            if head.strip():
                out.append(head.strip())
                self._buf = tail
        return out

    def flush(self) -> list[str]:
        rest = self._buf
        self._buf = ""
        return split_sentences(rest)


_YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "do it", "go ahead",
        "oui", "ouais", "confirme", "vas-y", "d'accord", "dacord", "نعم", "أكيد", "اكيد", "موافق"}
_NO = {"no", "nope", "nah", "not", "don't", "dont", "cancel", "stop", "wait", "abort",
       "non", "annule", "annuler", "arrête", "arrete", "لا", "إلغاء", "الغاء"}


def words(text: str) -> list[str]:
    return re.findall(r"[\w'’-]+", (text or "").lower().replace("’", "'"))


def parse_yes_no(text: str) -> bool | None:
    tokens = words(text)
    grams = set(tokens) | {" ".join(p) for p in zip(tokens, tokens[1:])}
    if grams & _NO:
        return False
    if grams & _YES:
        return True
    return None


def has_word(text: str, word: str) -> bool:
    return word.lower() in words(text)


def pcm16_from_wav(data: bytes, header_size: int = 44) -> bytes:
    pcm = data[header_size:] if data[:4] == b"RIFF" else data
    if len(pcm) % 2:
        pcm = pcm[:-1]
    return pcm
