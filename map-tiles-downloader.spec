# -*- mode: python ; coding: utf-8 -*-
import sys

# Select platform-specific icon
if sys.platform == 'win32':
    icon_file = 'img/icon_v2.ico'
elif sys.platform == 'darwin':
    icon_file = 'img/icon_v2.icns'
else:  # Linux and others
    icon_file = 'img/icon_v2.png'

a = Analysis(
    ['main.py'],
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
    name='map-tiles-downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
