import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

if os.environ.get("MARA_DATA_DIR"):
    LOG_DIR = Path(os.environ["MARA_DATA_DIR"]) / "logs"
else:
    LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MARA" / "logs"
LOG_FILE = LOG_DIR / "mara.log"
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

STARTUP_LOGGER = "mara.startup"

_configured = False


def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    logging.getLogger("mara").setLevel(logging.DEBUG)
    formatter = logging.Formatter(FORMAT)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    startup = logging.StreamHandler()
    startup.setLevel(logging.INFO)
    startup.setFormatter(logging.Formatter("%(message)s"))
    startup.addFilter(lambda r: r.name == STARTUP_LOGGER)
    root.addHandler(startup)

    if os.getenv("MARA_DEBUG") == "1":
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(formatter)
        console.addFilter(lambda r: r.name != STARTUP_LOGGER)
        root.addHandler(console)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mara.{name}")
