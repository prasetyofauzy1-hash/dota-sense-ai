import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DOTASENSE_OFFLINE", "true")
os.environ.setdefault("DOTASENSE_DATA_DIR", tempfile.mkdtemp(prefix="dotasense-data-"))
