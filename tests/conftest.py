import atexit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DOTASENSE_OFFLINE", "true")

if "DOTASENSE_DB_PATH" not in os.environ:
    _tmp_dir = tempfile.TemporaryDirectory(prefix="dotasense-test-")
    atexit.register(_tmp_dir.cleanup)
    os.environ["DOTASENSE_DB_PATH"] = str(Path(_tmp_dir.name) / "test.db")
