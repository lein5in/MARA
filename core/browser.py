import os
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from memory.credentials import credentials

# ─── Configurations des sites connus ─────────────────────────────────────────
# Ajouter un site ici = MARA peut s'y connecter automatiquement
SITE_CONFIGS = {
    "gmail": {
        "url": "https://mail.google.com",
        "steps": [
            {"action": "type",  "selector": 'input[type="email"]',    "credential": "email"},
            {"action": "click", "selector": "#identifierNext"},
            {"action": "wait",  "seconds": 1.5},
            {"action": "type",  "selector": 'input[type="password"]', "credential": "password"},
            {"action": "click", "selector": "#passwordNext"},
        ],
    },
    "brightspace": {
        "url": "https://brightspace.concordia.ca",
        "steps": [
            {"action": "type",  "selector": "#userNameInput",  "credential": "email"},
            {"action": "type",  "selector": "#passwordInput",  "credential": "password"},
            {"action": "click", "selector": "#submitButton"},
        ],
    },
    "outlook": {
        "url": "https://outlook.office.com",
        "steps": [
            {"action": "type",  "selector": 'input[type="email"]',    "credential": "email"},
            {"action": "click", "selector": 'input[type="submit"]'},
            {"action": "wait",  "seconds": 1.5},
            {"action": "type",  "selector": 'input[type="password"]', "credential": "password"},
            {"action": "click", "selector": 'input[type="submit"]'},
        ],
    },
}

BY_MAP = {
    "css":   By.CSS_SELECTOR,
    "xpath": By.XPATH,
    "id":    By.ID,
    "text":  By.LINK_TEXT,
    "name":  By.NAME,
}


# ─── BrowserController ────────────────────────────────────────────────────────

class BrowserController:
    """
    Contrôleur Chrome singleton.
    Lance un Chrome dédié MARA (profil séparé) avec remote debugging.
    Réutilise la même instance pour toutes les actions.
    """

    _instance = None
    _driver: webdriver.Chrome | None = None

    @classmethod
    def get_instance(cls) -> "BrowserController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── Driver management ────────────────────────────────────────────────────

    def _get_driver(self) -> webdriver.Chrome:
        """Retourne le driver existant ou lance un nouveau Chrome MARA."""
        if self._driver:
            try:
                _ = self._driver.title  # Vérifie si le driver est vivant
                return self._driver
            except WebDriverException:
                self._driver = None

        options = Options()

        # Dossier de profil MARA totalement indépendant — jamais de conflit avec Chrome ouvert
        mara_profile = Path(os.environ.get("LOCALAPPDATA", "")) / "MARA" / "ChromeProfile"
        mara_profile.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={mara_profile}")

        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-extensions")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        self._driver = webdriver.Chrome(options=options)
        print(f"[Browser] Chrome MARA lancé → profil : {mara_profile}")
        return self._driver

    # ─── Actions de base ──────────────────────────────────────────────────────

    def navigate(self, url: str) -> str:
        """Navigue vers une URL."""
        if not url.startswith("http"):
            url = "https://" + url
        self._get_driver().get(url)
        return f"Navigué vers : {url}"

    def click(self, selector: str, by: str = "css", timeout: int = 10) -> str:
        """Clique sur un élément — attend qu'il soit cliquable."""
        by_type = BY_MAP.get(by.lower(), By.CSS_SELECTOR)
        element = WebDriverWait(self._get_driver(), timeout).until(
            EC.element_to_be_clickable((by_type, selector))
        )
        element.click()
        return f"Cliqué : {selector}"

    def type_text(self, selector: str, text: str, by: str = "css", timeout: int = 10, clear: bool = True) -> str:
        """Tape du texte dans un champ — attend qu'il soit présent."""
        by_type = BY_MAP.get(by.lower(), By.CSS_SELECTOR)
        element = WebDriverWait(self._get_driver(), timeout).until(
            EC.presence_of_element_located((by_type, selector))
        )
        if clear:
            element.clear()
        element.send_keys(text)
        return f"Texte saisi."

    def wait_for(self, selector: str, by: str = "css", timeout: int = 10) -> str:
        """Attend qu'un élément soit présent dans le DOM."""
        by_type = BY_MAP.get(by.lower(), By.CSS_SELECTOR)
        WebDriverWait(self._get_driver(), timeout).until(
            EC.presence_of_element_located((by_type, selector))
        )
        return f"Élément détecté : {selector}"

    def read_element(self, selector: str, by: str = "css", timeout: int = 10) -> str:
        """Lit le texte d'un élément spécifique et le retourne."""
        by_type = BY_MAP.get(by.lower(), By.CSS_SELECTOR)
        element = WebDriverWait(self._get_driver(), timeout).until(
            EC.presence_of_element_located((by_type, selector))
        )
        return element.text

    def read_page(self, max_chars: int = 2000) -> str:
        """
        Lit le contenu principal de la page sans sélecteur.
        Essaie d'extraire le texte utile (pas les scripts, nav, footer).
        Retourne un résumé tronqué du contenu visible.
        """
        driver = self._get_driver()
        title = driver.title

        # Essaie les conteneurs de contenu principal en priorité
        main_selectors = [
            "main", "article", "#content", ".content",
            "#main-content", ".main-content", "#results",
            "ytd-video-renderer", ".ytd-video-renderer",  # YouTube
            "[role='main']",
        ]

        text = ""
        for sel in main_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    text = " | ".join(
                        e.text.strip()
                        for e in elements[:5]
                        if e.text.strip()
                    )
                    if text:
                        break
            except Exception:
                continue

        # Fallback — body entier si rien trouvé
        if not text:
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                text = body.text.strip()
            except Exception:
                text = ""

        # Nettoie et tronque
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        clean = " | ".join(lines)[:max_chars]

        return f"Page : {title}\n{clean}" if clean else f"Page : {title} (contenu non lisible)"

    def get_page_title(self) -> str:
        return self._get_driver().title

    def close(self) -> str:
        """Ferme le navigateur MARA."""
        if self._driver:
            self._driver.quit()
            self._driver = None
        return "Navigateur fermé."

    # ─── Login automatique ────────────────────────────────────────────────────

    def login(self, site: str) -> str:
        """
        Connexion automatique à un site connu.
        Utilise les credentials stockés dans mara_credentials.enc.
        """
        config = SITE_CONFIGS.get(site.lower())
        if not config:
            return f"Site inconnu : {site}. Sites supportés : {', '.join(SITE_CONFIGS.keys())}"

        if not credentials.has_credentials(site):
            return (
                f"No credentials stored for {site}. "
                f"Say 'save credentials for {site}' to register them."
            )

        email    = credentials.get_email(site)
        password = credentials.get_password(site)

        self.navigate(config["url"])

        for step in config["steps"]:
            action = step["action"]

            if action == "type":
                credential_key = step.get("credential")
                text = email if credential_key == "email" else password
                self.type_text(step["selector"], text)

            elif action == "click":
                self.click(step["selector"])

            elif action == "wait":
                time.sleep(step.get("seconds", 1))

        return f"Logged into {site}."

    # ─── Gestion des credentials ──────────────────────────────────────────────

    def save_credential(self, site: str, email: str, password: str) -> str:
        """Sauvegarde les identifiants dans mara_credentials.enc (Fernet AES)."""
        return credentials.save(site, email, password)

    def get_credential(self, site: str, field: str) -> str | None:
        """Récupère un identifiant depuis mara_credentials.enc."""
        if field == "email":
            return credentials.get_email(site)
        return credentials.get_password(site)

    def delete_credential(self, site: str) -> str:
        """Supprime les identifiants d'un site."""
        return credentials.delete(site)


# ─── Singleton global ─────────────────────────────────────────────────────────
browser = BrowserController.get_instance()