import time
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from memory.credentials import get_credentials
from core.config import BROWSER_TIMEOUT, CHROME_PROFILE_DIR
from core.log import get_logger
log = get_logger(__name__)


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


class BrowserController:
    def __init__(self):
        self._driver: webdriver.Chrome | None = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._driver is not None

    def _get_driver(self) -> webdriver.Chrome:
        if self._driver:
            try:
                _ = self._driver.title
                return self._driver
            except WebDriverException:
                self._driver = None

        options = Options()
        CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-extensions")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        self._driver = webdriver.Chrome(options=options)
        log.info(f"[Browser] MARA Chrome started, profile: {CHROME_PROFILE_DIR}")
        return self._driver

    def _by(self, by: str):
        return BY_MAP.get((by or "css").lower(), By.CSS_SELECTOR)

    def navigate(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        self._get_driver().get(url)
        return f"Opened {url} (title: {self._driver.title})."

    def click(self, selector: str, by: str = "css", timeout: int = BROWSER_TIMEOUT) -> str:
        element = WebDriverWait(self._get_driver(), timeout).until(
            EC.element_to_be_clickable((self._by(by), selector))
        )
        element.click()
        return f"Clicked {selector}."

    def type_text(self, selector: str, text: str, by: str = "css", timeout: int = BROWSER_TIMEOUT, clear: bool = True) -> str:
        element = WebDriverWait(self._get_driver(), timeout).until(
            EC.presence_of_element_located((self._by(by), selector))
        )
        if clear:
            element.clear()
        element.send_keys(text)
        return "Text entered."

    def wait_for(self, selector: str, by: str = "css", timeout: int = BROWSER_TIMEOUT) -> str:
        WebDriverWait(self._get_driver(), timeout).until(
            EC.presence_of_element_located((self._by(by), selector))
        )
        return f"Element present: {selector}."

    def read_element(self, selector: str, by: str = "css", timeout: int = BROWSER_TIMEOUT) -> str:
        element = WebDriverWait(self._get_driver(), timeout).until(
            EC.presence_of_element_located((self._by(by), selector))
        )
        return element.text

    def read_page(self, max_chars: int = 4000) -> str:
        driver = self._get_driver()
        title = driver.title
        main_selectors = [
            "main", "article", "#content", ".content",
            "#main-content", ".main-content", "#results",
            "ytd-video-renderer", "[role='main']",
        ]
        text = ""
        for sel in main_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                text = " | ".join(e.text.strip() for e in elements[:5] if e.text.strip())
                if text:
                    break
            except WebDriverException:
                continue
        if not text:
            try:
                text = driver.find_element(By.TAG_NAME, "body").text.strip()
            except WebDriverException:
                text = ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        clean = " | ".join(lines)[:max_chars]
        return f"Page: {title}\n{clean}" if clean else f"Page: {title} (no readable content)"

    def close(self) -> str:
        with self._lock:
            driver, self._driver = self._driver, None
        if driver:
            try:
                driver.quit()
            except Exception as e:
                log.warning(f"[Browser] quit failed: {e}")
        return "Browser closed."

    def login(self, site: str) -> str:
        config = SITE_CONFIGS.get(site.lower())
        if not config:
            return f"Unknown site: {site}. Supported: {', '.join(SITE_CONFIGS)}."
        credentials = get_credentials()
        if not credentials.has_credentials(site):
            return f"No credentials stored for {site}. Ask the user to save them first."

        email = credentials.get_email(site)
        password = credentials.get_password(site)
        self.navigate(config["url"])
        for step in config["steps"]:
            action = step["action"]
            if action == "type":
                text = email if step.get("credential") == "email" else password
                self.type_text(step["selector"], text)
            elif action == "click":
                self.click(step["selector"])
            elif action == "wait":
                time.sleep(step.get("seconds", 1))
        return f"Logged into {site}."


browser = BrowserController()
