# -*- mode: python ; coding: utf-8 -*-

import os


runtime_tmpdir = os.path.join(
    os.environ.get("LOCALAPPDATA", "."),
    "iCloud_aio_tool",
)

a = Analysis(
    ['iCloud_aio_tool.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='iCloud_aio_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    runtime_tmpdir=runtime_tmpdir,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
