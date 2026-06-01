# PyInstaller spec — macOS .app + DMG (no Apple Developer ID)
# Build: ./scripts/build_mac_installer.sh

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
root = Path(SPECPATH)

hiddenimports = collect_submodules("screen_gif_recorder")
hiddenimports += [
    "sounddevice",
    "numpy",
    "imageio",
    "imageio_ffmpeg",
    "PIL",
    "PIL.Image",
    "mss",
    "objc",
    "AppKit",
    "Quartz",
    "CoreFoundation",
    "ApplicationServices",
]

datas: list = []
binaries: list = []

for pkg in ("AppKit", "Quartz", "ApplicationServices", "objc"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

for pkg in ("sounddevice", "imageio_ffmpeg", "PyQt6"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["run.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pixly",
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
    name="Pixly",
)

app = BUNDLE(
    coll,
    name="Pixly.app",
    icon=None,
    bundle_identifier="com.pixly.screen-gif-recorder",
    info_plist={
        "CFBundleName": "Pixly",
        "CFBundleDisplayName": "Pixly",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSScreenCaptureUsageDescription": (
            "Pixly records the screen region you select to create GIF or MP4 files."
        ),
        "NSMicrophoneUsageDescription": (
            "Pixly can record microphone audio into MP4 exports."
        ),
        "LSMinimumSystemVersion": "11.0",
    },
)
