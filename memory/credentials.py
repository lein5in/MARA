import json
from pathlib import Path
from cryptography.fernet import Fernet


CREDENTIALS_DIR  = Path(__file__).parent
KEY_PATH         = CREDENTIALS_DIR / "mara.key"
CREDENTIALS_PATH = CREDENTIALS_DIR / "mara_credentials.enc"




class CredentialsManager:
    """
    Stockage chiffré des identifiants MARA.
    Même approche que la mémoire — Fernet AES local, jamais en clair.
    Structure : { "gmail": {"email": "...", "password": "..."}, ... }
    """

    def __init__(self):
        self._key  = self._load_or_create_key()
        self._fernet = Fernet(self._key)
        self._data = self._load()

     

    def _load_or_create_key(self) -> bytes:
        if KEY_PATH.exists():
            return KEY_PATH.read_bytes()
        key = Fernet.generate_key()
        KEY_PATH.write_bytes(key)
        print("[Credentials] Clé générée.")
        return key


    def _load(self) -> dict:
        if not CREDENTIALS_PATH.exists():
            return {}
        try:
            encrypted = CREDENTIALS_PATH.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            print(f"[Credentials] Erreur chargement : {e}")
            return {}

    def _save(self):
        raw = json.dumps(self._data, ensure_ascii=False).encode()
        encrypted = self._fernet.encrypt(raw)
        CREDENTIALS_PATH.write_bytes(encrypted)

    

    def save(self, site: str, email: str, password: str) -> str:
        """Sauvegarde les identifiants d'un site."""
        self._data[site.lower()] = {"email": email, "password": password}
        self._save()
        print(f"[Credentials] Sauvegardé : {site}")
        return f"Credentials for {site} saved securely."

    def get_email(self, site: str) -> str | None:
        return self._data.get(site.lower(), {}).get("email")

    def get_password(self, site: str) -> str | None:
        return self._data.get(site.lower(), {}).get("password")

    def delete(self, site: str) -> str:
        """Supprime les identifiants d'un site."""
        if site.lower() in self._data:
            del self._data[site.lower()]
            self._save()
            return f"Credentials for {site} deleted."
        return f"No credentials found for {site}."

    def list_sites(self) -> list[str]:
        """Retourne la liste des sites avec des identifiants stockés."""
        return list(self._data.keys())

    def has_credentials(self, site: str) -> bool:
        return site.lower() in self._data



credentials = CredentialsManager()