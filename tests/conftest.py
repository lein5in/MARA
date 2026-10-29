import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="mara-tests-")
os.environ["MARA_DATA_DIR"] = _TMP
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["FISH_API_KEY"] = "test-key"
os.environ["USER_NAME"] = "Tester"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
