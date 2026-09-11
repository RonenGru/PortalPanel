# -*- mode: python ; coding: utf-8 -*-
# PortalPanel - PyInstaller spec (two executables)
#
# IMPORTANT: each executable gets its OWN Analysis + PYZ. If both entry
# scripts are fed into a single Analysis and share one PYZ, PyInstaller marks
# only the first script as __main__, so the other exe's `if __name__ ==
# "__main__":` block is silently skipped (server never starts). Separate
# analyses fix this. Both exes still land in one dist/PortalPanel folder via
# a single COLLECT at the end.
import os

ROOT = r"E:\Videos\PortalPanel_Final"
SP   = os.path.join(ROOT, "venv", "Lib", "site-packages")

MANAGER  = os.path.join(ROOT, "manager")
PATHEX   = [ROOT, MANAGER]
DATAS    = [
    # SimConnect.dll must sit next to SimConnect.py inside _internal/SimConnect/
    (os.path.join(SP, "SimConnect", "SimConnect.dll"), "SimConnect"),
]
HIDDEN   = [
    "flask_socketio", "python_engineio", "simple_websocket", "bidict",
    "webview", "screeninfo",
    # engineio resolves its async driver via a DYNAMIC import
    # (importlib.import_module('engineio.async_drivers.' + mode)), which
    # PyInstaller's static analysis can't see -> module missing at runtime ->
    # "Invalid async_mode specified". Force-bundle the threading driver.
    "engineio.async_drivers.threading",
]
EXCLUDES = ["tkinter", "matplotlib", "numpy", "pandas"]

# ---- Entry point 1: the server (PortalPanelServer.exe) ----
a_server = Analysis(
    [os.path.join(MANAGER, "portalpanel_server.py")],
    pathex=PATHEX,
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
)
pyz_server = PYZ(a_server.pure)
exe_server = EXE(
    pyz_server, a_server.scripts, [],
    exclude_binaries=True,
    name="PortalPanelServer",
    icon=os.path.join(ROOT, "logo.ico"),
    console=True,          # keep console for logs during testing
)

# ---- Entry point 2: the launcher (PortalPanelLauncher.exe) ----
a_launcher = Analysis(
    [os.path.join(MANAGER, "portalpanel.py")],
    pathex=PATHEX,
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
)
pyz_launcher = PYZ(a_launcher.pure)
exe_launcher = EXE(
    pyz_launcher, a_launcher.scripts, [],
    exclude_binaries=True,
    name="PortalPanelLauncher",
    icon=os.path.join(ROOT, "logo.ico"),
    console=True,          # keep console for now; switch to False for release build
)

# Both exes + their binaries/datas into one folder.
coll = COLLECT(
    exe_server, exe_launcher,
    a_server.binaries, a_server.datas,
    a_launcher.binaries, a_launcher.datas,
    strip=False, upx=False,
    name="PortalPanel",
)
