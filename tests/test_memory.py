import json
import sys
import threading
import uuid

import pytest
from cryptography.fernet import Fernet

from core import storage
from memory import keystore
from memory.memory import MemoryStore, worth_extracting


@pytest.fixture
def fernet():
    return Fernet(Fernet.generate_key())


def write_memory(path, fernet, data):
    path.write_bytes(fernet.encrypt(json.dumps(data).encode()))


def test_corrupt_file_is_backed_up_and_memory_starts_empty(tmp_path, fernet):
    path = tmp_path / "mara_memory.enc"
    path.write_bytes(b"not encrypted at all")
    store = MemoryStore(path, fernet)
    assert store.items() == {"facts": [], "preferences": [], "context": []}
    backups = list(tmp_path.glob("mara_memory.enc.*.corrupt"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"not encrypted at all"
    assert path.read_bytes() == b"not encrypted at all"
    store.add_fact("Habib studies computer science")
    assert backups[0].exists()


def test_wrong_key_is_treated_like_corruption(tmp_path, fernet):
    path = tmp_path / "m.enc"
    write_memory(path, Fernet(Fernet.generate_key()), {"user": {"facts": ["x"]}})
    MemoryStore(path, fernet)
    assert list(tmp_path.glob("m.enc.*.corrupt"))


def test_crash_during_write_keeps_previous_file(tmp_path, fernet, monkeypatch):
    path = tmp_path / "m.enc"
    store = MemoryStore(path, fernet)
    store.add_fact("First fact about the user")

    def boom(src, dst):
        raise OSError("disk unplugged")
    monkeypatch.setattr(storage.os, "replace", boom)
    store.add_fact("Second fact that never hits the disk")
    monkeypatch.undo()
    reloaded = MemoryStore(path, fernet)
    assert reloaded.items()["facts"] == ["First fact about the user"]
    assert not list(tmp_path.glob("*.tmp"))


def test_legacy_string_entries_are_upgraded(tmp_path, fernet):
    path = tmp_path / "m.enc"
    write_memory(path, fernet, {"user": {"name": "H", "facts": ["Likes tea"], "preferences": []}, "context": ["Exam"],
                                "paused_until": None})
    store = MemoryStore(path, fernet)
    assert store.items()["facts"] == ["Likes tea"]
    store.add_fact("Lives in Montreal")
    entries = store.entries("facts")
    assert entries[-1]["added"] and entries[0]["text"] == "Likes tea"


def test_caps_and_timestamps(tmp_path, fernet):
    store = MemoryStore(tmp_path / "m.enc", fernet, caps={"facts": 3, "preferences": 3, "context": 3})
    for text in ("Owns a bicycle", "Speaks Arabic fluently", "Was born in Dakar", "Plays chess on weekends",
                 "Works nights"):
        store.add_fact(text)
    facts = store.items()["facts"]
    assert facts == ["Was born in Dakar", "Plays chess on weekends", "Works nights"]
    assert all(e["added"] for e in store.entries("facts"))


def test_near_duplicates_are_consolidated(tmp_path, fernet):
    store = MemoryStore(tmp_path / "m.enc", fernet)
    store.add_fact("Habib is a computer science co-op student")
    store.add_fact("Habib is a computer science co-op student.")
    store.add_fact("Habib is a Computer Science co-op student at Concordia")
    store.add_preference("Prefers short answers")
    assert store.items()["facts"] == ["Habib is a Computer Science co-op student at Concordia"]
    assert store.items()["preferences"] == ["Prefers short answers"]


def test_concurrent_writes(tmp_path, fernet):
    store = MemoryStore(tmp_path / "m.enc", fernet, caps={"facts": 500, "preferences": 5, "context": 5})
    threads = [threading.Thread(target=store.add_fact, args=(uuid.uuid4().hex,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(MemoryStore(tmp_path / "m.enc", fernet).items()["facts"]) == 30


@pytest.mark.parametrize("text, expected", [
    ("ok", False), ("merci", False), ("ok merci beaucoup", False), ("thank you so much", False),
    ("My password is hunter2 for gmail", False), ("mon mot de passe est azerty123", False),
    ("I just started a new job at Hydro-Québec", True), ("J'adore le café le matin", True),
])
def test_worth_extracting(text, expected):
    assert worth_extracting(text) is expected


@pytest.fixture
def fake_dpapi(monkeypatch):
    monkeypatch.setattr(keystore, "_dpapi_protect", lambda data: b"P:" + data[::-1])

    def unprotect(data):
        if not data.startswith(b"P:"):
            raise keystore.KeyStoreError("bad blob")
        return data[2:][::-1]
    monkeypatch.setattr(keystore, "_dpapi_unprotect", unprotect)


def test_dpapi_migration_is_lossless(tmp_path, fake_dpapi):
    key = Fernet.generate_key()
    plain, protected, enc = tmp_path / "mara.key", tmp_path / "mara.key.dpapi", tmp_path / "mara_memory.enc"
    plain.write_bytes(key)
    enc.write_bytes(Fernet(key).encrypt(b"{}"))
    assert keystore.load_key(plain, protected, [enc]) == key
    assert protected.exists() and not plain.exists()
    assert (tmp_path / "mara.key.bak").read_bytes() == key
    assert keystore.load_key(plain, protected, [enc]) == key


def test_dpapi_migration_refuses_wrong_key(tmp_path, fake_dpapi):
    plain, protected, enc = tmp_path / "mara.key", tmp_path / "mara.key.dpapi", tmp_path / "mara_memory.enc"
    plain.write_bytes(Fernet.generate_key())
    enc.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"{}"))
    keystore.load_key(plain, protected, [enc])
    assert plain.exists() and not protected.exists()


def test_dpapi_roundtrip_failure_keeps_plaintext(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    plain, protected = tmp_path / "mara.key", tmp_path / "mara.key.dpapi"
    plain.write_bytes(key)
    monkeypatch.setattr(keystore, "_dpapi_protect", lambda d: b"garbage")
    monkeypatch.setattr(keystore, "_dpapi_unprotect", lambda d: b"other")
    assert keystore.load_key(plain, protected, []) == key
    assert plain.exists() and not protected.exists()


def test_existing_backup_is_never_overwritten(tmp_path, fake_dpapi):
    key = Fernet.generate_key()
    plain, protected = tmp_path / "mara.key", tmp_path / "mara.key.dpapi"
    plain.write_bytes(key)
    (tmp_path / "mara.key.bak").write_bytes(b"older backup")
    keystore.load_key(plain, protected, [])
    assert (tmp_path / "mara.key.bak").read_bytes() == b"older backup"
    assert any(p.read_bytes() == key for p in tmp_path.glob("mara.key.bak.*"))


def test_new_key_is_protected(tmp_path, fake_dpapi):
    plain, protected = tmp_path / "mara.key", tmp_path / "mara.key.dpapi"
    key = keystore.load_key(plain, protected, [])
    assert not plain.exists() and protected.read_bytes() == b"P:" + key[::-1]


def test_unprotect_failure_falls_back_to_plaintext(tmp_path, fake_dpapi):
    key = Fernet.generate_key()
    plain, protected = tmp_path / "mara.key", tmp_path / "mara.key.dpapi"
    plain.write_bytes(key)
    protected.write_bytes(b"corrupted")
    assert keystore.load_key(plain, protected, []) == key


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_real_dpapi_roundtrip():
    secret = Fernet.generate_key()
    blob = keystore._dpapi_protect(secret)
    assert blob != secret and keystore._dpapi_unprotect(blob) == secret


def test_legacy_migration_skips_key_once_protected(tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "mara.key").write_bytes(b"k")
    data = tmp_path / "data"
    storage.migrate_legacy_data(data, key=None, encrypted=[], plain=[])
    assert not (data / "mara.key").exists()
