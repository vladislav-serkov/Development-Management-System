# PyInstaller spec for Extract Agent backend sidecar
# Build:  pyinstaller --clean --noconfirm backend.spec
# Output: dist/extract-agent-backend/extract-agent-backend (--onedir)

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("anthropic")
hiddenimports += collect_submodules("pydantic")
hiddenimports += collect_submodules("aiofiles")
hiddenimports += collect_submodules("httpx")
hiddenimports += [
    "httptools",
    "websockets",
    "wsproto",
    "h11",
    "email_validator",
    "multipart",
    "python_multipart",
]

a = Analysis(
    ["app/sidecar.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="extract-agent-backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="extract-agent-backend",
)
