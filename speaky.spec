# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['speaky/main.py'],
    pathex=[],
    binaries=[],
    datas=[('speaky/locales', 'speaky/locales'), ('resources', 'resources')],
    hiddenimports=['PyQt5.sip', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'pynput.keyboard', 'pynput.keyboard._xorg', 'pynput.keyboard._win32', 'pynput.keyboard._darwin', 'yaml', 'numpy', 'websockets'],
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
    name='speaky',
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
)
