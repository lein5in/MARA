import json
import threading

from cryptography.fernet import Fernet

from core.config import CREDENTIALS_PATH
from core.storage import atomic_write_bytes
from core.log import get_logger
log = get_logger(__name__)


class CredentialsManager:
    def __init__(self, path=CREDENTIALS_PATH, fernet: Fernet | None = None):
        if fernet is None:
            from memory.keystore import get_key
            fernet = Fernet(get_key())
        self._path = path
        self._fernet = fernet
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._fernet.decrypt(self._path.read_bytes()).decode())
        except Exception as e:
            log.error(f"[Credentials] Could not read the vault: {type(e).__name__}")
            return {}

    def _save(self):
        raw = json.dumps(self._data, ensure_ascii=False).encode()
        atomic_write_bytes(self._path, self._fernet.encrypt(raw))

    def save(self, site: str, email: str, password: str) -> str:
        with self._lock:
            self._data[site.lower()] = {"email": email, "password": password}
            self._save()
        log.info(f"[Credentials] Saved credentials for {site}")
        return f"Credentials for {site} saved securely."

    def get_email(self, site: str) -> str | None:
        return self._data.get(site.lower(), {}).get("email")

    def get_password(self, site: str) -> str | None:
        return self._data.get(site.lower(), {}).get("password")

    def delete(self, site: str) -> str:
        with self._lock:
            if site.lower() not in self._data:
                return f"No credentials found for {site}."
            del self._data[site.lower()]
            self._save()
        return f"Credentials for {site} deleted."

    def has_credentials(self, site: str) -> bool:
        return site.lower() in self._data


_instance: CredentialsManager | None = None
_instance_lock = threading.Lock()


def get_credentials() -> CredentialsManager:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CredentialsManager()
    return _instance
