# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — macOS .app with bundled sound/
# Run: pyinstaller slap-your-mac.spec

block_cipher = None

a = Analysis(
    ["slap_detector.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("sound/mhhh.wav", "sound"),
        ("sound/ahShort.wav", "sound"),
    ],
    hiddenimports=[
        "numpy",
        "numpy.core._multiarray_umath",
        "sounddevice",
        "_sounddevice",
        "_sounddevice_data",
        "macimu",
        "macimu._spu",
        "macimu.orientation",
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
    argv_emulation=True,
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

app = BUNDLE(
    coll,
    name="SlapYourMac.app",
    icon=None,
    bundle_identifier="dev.slapyourmac.detector",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": (
            "SlapYourMac listens for sharp taps on your laptop so it can play sounds in response."
        ),
    },
)
