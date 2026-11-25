import atexit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DOTASENSE_OFFLINE", "true")

_tmp_dir = tempfile.TemporaryDirectory(prefix="dotasense-test-")
atexit.register(_tmp_dir.cleanup)
os.environ.setdefault("DOTASENSE_DATA_DIR", _tmp_dir.name)
os.environ.setdefault("DOTASENSE_DB_PATH", str(Path(_tmp_dir.name) / "test.db"))
