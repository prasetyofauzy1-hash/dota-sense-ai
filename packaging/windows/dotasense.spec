# PyInstaller spec for the Windows app: `pyinstaller packaging/windows/dotasense.spec --noconfirm`
import glob
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = [
    (os.path.join(ROOT, "app", "dashboard.py"), "app"),
    (os.path.join(ROOT, "app", "data", "snapshot"), os.path.join("app", "data", "snapshot")),
    (os.path.join(ROOT, "config", "mock_scenarios"), os.path.join("config", "mock_scenarios")),
    (os.path.join(ROOT, ".streamlit", "config.toml"), ".streamlit"),
]
datas += collect_data_files("streamlit") + copy_metadata("streamlit")
# dashboard.py runs as a Streamlit script, so its imports are invisible to the analysis: list every app module.
app_modules = sorted(
    ".".join(Path(path).relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
    for path in glob.glob(os.path.join(ROOT, "app", "**", "*.py"), recursive=True)
    if not path.endswith("dashboard.py")
)
hiddenimports = app_modules + collect_submodules("uvicorn") + collect_submodules("streamlit")

a = Analysis(
    [os.path.join(SPECPATH, "dotasense_launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "playwright", "IPython", "matplotlib"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DotaSenseAI",
    icon=os.path.join(SPECPATH, "dotasense.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DotaSenseAI", upx=False)
