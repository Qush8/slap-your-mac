# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — Windows microphone build (bundled sound/)
# Run on Windows (with venv + pyinstaller): pyinstaller slap-your-mac-win.spec

block_cipher = None

a = Analysis(
    ["slap_detector.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("sound/mhhh.m4a", "sound"),
        ("sound/ahShort.m4a", "sound"),
    ],
    hiddenimports=[
        "numpy",
        "numpy.core._multiarray_umath",
        "sounddevice",
        "_sounddevice",
        "_sounddevice_data",
        "playsound",
        "cffi",
        "_cffi_backend",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SlapYourMac",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SlapYourMac",
)
