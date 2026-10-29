import ctypes
import os
import sys
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from core.config import KEY_PATH, KEY_PROTECTED_PATH, MEMORY_PATH, CREDENTIALS_PATH
from core.storage import atomic_write_bytes
from core.log import get_logger
log = get_logger(__name__)


class KeyStoreError(Exception):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _crypt(fn_name: str, data: bytes) -> bytes:
    if sys.platform != "win32":
        raise KeyStoreError("DPAPI is only available on Windows")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    blob_in, _keep = _blob(data)
    blob_out = _Blob()
    fn = getattr(crypt32, fn_name)
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out))
    if not ok:
        raise KeyStoreError(f"{fn_name} failed (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_protect(data: bytes) -> bytes:
    return _crypt("CryptProtectData", data)


def _dpapi_unprotect(data: bytes) -> bytes:
    return _crypt("CryptUnprotectData", data)


def _backup_name(path: Path) -> Path:
    candidate = path.with_name(path.name + ".bak")
    if not candidate.exists():
        return candidate
    return path.with_name(f"{path.name}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")


def _decrypts_all(key: bytes, files: list[Path]) -> bool:
    fernet = Fernet(key)
    for f in files:
        if f.exists():
            try:
                fernet.decrypt(f.read_bytes())
            except (InvalidToken, ValueError):
                log.error(f"[Key] {f.name} cannot be decrypted with the current key")
                return False
    return True


def load_key(plain_path: Path = KEY_PATH, protected_path: Path = KEY_PROTECTED_PATH,
             encrypted_files: list[Path] | None = None) -> bytes:
    files = encrypted_files if encrypted_files is not None else [MEMORY_PATH, CREDENTIALS_PATH]

    if protected_path.exists():
        try:
            return _dpapi_unprotect(protected_path.read_bytes())
        except Exception as e:
            log.error(f"[Key] Could not unprotect {protected_path.name}: {e}")
            if plain_path.exists():
                log.warning("[Key] Falling back to the plaintext key.")
                return plain_path.read_bytes().strip()
            raise

    if plain_path.exists():
        key = plain_path.read_bytes().strip()
        try:
            migrate(key, plain_path, protected_path, files)
        except Exception as e:
            log.error(f"[Key] DPAPI migration skipped, still using the plaintext key: {e}")
        return key

    key = Fernet.generate_key()
    atomic_write_bytes(protected_path, _dpapi_protect(key))
    log.info("[Key] New memory key generated and protected with DPAPI.")
    return key


def migrate(key: bytes, plain_path: Path, protected_path: Path, files: list[Path]):
    if not _decrypts_all(key, files):
        raise KeyStoreError("the plaintext key does not decrypt the existing data")
    atomic_write_bytes(protected_path, _dpapi_protect(key))
    try:
        restored = _dpapi_unprotect(protected_path.read_bytes())
        if restored != key or not _decrypts_all(restored, files):
            raise KeyStoreError("protected key does not round-trip")
    except Exception:
        try:
            os.unlink(protected_path)
        except OSError:
            pass
        raise
    backup = _backup_name(plain_path)
    os.replace(plain_path, backup)
    log.info(f"[Key] Key now protected with DPAPI. Old plaintext key kept as {backup.name}.")


_cached: bytes | None = None


def get_key() -> bytes:
    global _cached
    if _cached is None:
        _cached = load_key()
    return _cached
