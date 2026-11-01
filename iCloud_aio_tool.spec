# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_data_files


fido2_datas = collect_data_files("fido2")

a = Analysis(
    ['iCloud_aio_tool.py'],
    pathex=[],
    binaries=[],
    datas=fido2_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
is_macos = sys.platform == 'darwin'
binary_args = [] if is_macos else [a.binaries, a.datas]

exe = EXE(
    pyz,
    a.scripts,
    *binary_args,
    [],
    exclude_binaries=is_macos,
    name='iCloud_aio_tool',
    icon='assets/app.icns' if sys.platform == 'darwin' else 'assets/app.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    runtime_tmpdir=None,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if is_macos:
    collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name='iCloud_aio_tool')
    app = BUNDLE(
        collection,
        name='iCloud File Downloading Tool.app',
        icon='assets/app.icns',
        bundle_identifier='org.icloud-file-downloader.desktop',
        info_plist={
            'CFBundleDisplayName': 'iCloud File Downloading Tool',
            'NSHighResolutionCapable': True,
        },
    )
