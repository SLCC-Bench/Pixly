# Pixly — Screen to GIF Recorder (macOS)

Record a selected region of your screen and export as an optimized **GIF** or **MP4**. Built with Python 3.10+, PyQt6, and `mss` for fast capture. Retina regions are captured at full physical resolution when Screen Recording permission is granted.

## Features

- Click-and-drag region selection overlay
- Real-time capture with FPS, resolution scale (1× / 0.75× / 0.5×), and quality vs size slider
- GIF export with adaptive palette (≤256 colors) and optional frame thinning
- **Browser Tab** picker — record a Chrome, Safari, Firefox, Arc, etc. window (tab title = window name)
- MP4 export via `ffmpeg` or bundled `imageio-ffmpeg`
- Non-blocking UI (capture and export on background threads)
- Keyboard shortcuts: **⌘R** start, **⌘.** stop
- Optional copy GIF to clipboard after save
- **MP4 audio**: optional microphone + system audio (system audio via BlackHole loopback on macOS)

## Requirements

- macOS 11+ (Intel or Apple Silicon)
- Python 3.10 or newer
- [Screen Recording permission](https://support.apple.com/guide/mac-help/control-access-screen-system-audio-recording-mchld6aa7d23/mac) for Terminal, Python, or the packaged `.app`
- **MP4 export**: included via `imageio-ffmpeg`, or install system ffmpeg: `brew install ffmpeg`
- **Browser Tab** uses AppleScript (Chrome/Safari/etc. must be running)

## Install

```bash
cd /path/to/Pixly
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

From the project root (so imports resolve):

```bash
python run.py
```

Or as a module:

```bash
python -m screen_gif_recorder.main
```

### First launch — permissions

1. Start the app and click **Select Area**.
2. If capture is black or fails, open **System Settings → Privacy & Security → Screen Recording**.
3. Enable **Terminal** (or **Python**, or **Pixly.app** after packaging).
4. Quit and restart the app.

## Usage

1. Choose what to record:
   - **Browser Tab** — pick a browser window (e.g. your open tab in Chrome)
   - **Select Area** — drag a rectangle; confirm with **Use this region**
   - **Select display** — pick which monitor to record (multi-screen setups)
2. Adjust **FPS**, **Resolution**, and **Quality vs size** as needed.
3. **Start Recording** (or ⌘R), then **Stop Recording** (or ⌘.) — app minimizes while recording.
4. **Save as GIF** or **Save as MP4** (audio is muxed into MP4 only).

### Audio (MP4)

- Enable **Record microphone** and/or **Record system audio** in the Audio panel before recording.
- Use **Mute** checkboxes to silence a source while recording (or toggle mute during capture).
- **System audio** on macOS requires a loopback device (e.g. [BlackHole 2ch](https://existential.audio/blackhole/)): install it, set Mac output to BlackHole, then enable **Record system audio**.
- Grant **Microphone** access in System Settings if prompted.

Lower quality values drop more frames during GIF export for smaller files. Resolution scaling applies during capture (smaller files, less CPU).

## Project layout

```
Pixly/
├── run.py                      # Launcher
├── requirements.txt
├── pixly.spec                  # PyInstaller bundle spec
├── screen_gif_recorder/
│   ├── main.py
│   ├── capture/screen_recorder.py
│   ├── export/gif_exporter.py, mp4_exporter.py
│   ├── ui/main_window.py, region_selector.py, workers.py
│   └── utils/permissions.py, temp_files.py
└── README.md
```

## UI design (Figma)

A Figma handoff spec lives at [`design/PIXLY_UI_FIGMA.md`](design/PIXLY_UI_FIGMA.md) with colors, typography, spacing, and layout for a **680×820** main window. Use it in Figma or Figma Make to iterate on visuals; the running app is implemented in PyQt6 via [`screen_gif_recorder/ui/styles.py`](screen_gif_recorder/ui/styles.py).

## Build macOS installer (no Apple Developer ID)

Creates `dist/Pixly.app` and a drag-to-Applications DMG with **ad-hoc** signing (`codesign -s -`). No paid Apple Developer account required. Recipients use **Right-click → Open** the first time.

```bash
./scripts/build_mac_installer.sh
```

Output example:

- `dist/Pixly.app`
- `dist/Pixly-1.0.0-macOS-arm64.dmg` (or `x86_64` on Intel Macs)

See `packaging/INSTALL.txt` for end-user install steps bundled in the DMG.

### Manual PyInstaller build

```bash
source .venv/bin/activate
pip install -r requirements-build.txt
pyinstaller pixly.spec --noconfirm
codesign --force --deep --sign - dist/Pixly.app
```

Grant **Screen Recording** for **Pixly** in System Settings when prompted.

### Code signing with a Developer ID (optional)

If you have a paid Apple Developer account:

```bash
codesign --force --deep --sign "Developer ID Application: Your Name" dist/Pixly.app
xcrun notarytool submit dist/Pixly-*.dmg --apple-id ... --team-id ... --password ...
```

## Build with py2app (alternative)

```bash
pip install py2app
```

Create `setup.py` with `py2app` entry pointing at `run.py`, then:

```bash
python setup.py py2app
```

PyInstaller is recommended for simpler one-command builds with the included `pixly.spec`.

## Troubleshooting

| Issue | Fix |
|--------|-----|
| Black frames | Grant Screen Recording permission and restart |
| MP4 button disabled | Install ffmpeg: `brew install ffmpeg` |
| Large GIF files | Lower FPS, use 0.5× scale, reduce quality slider |
| UI lag during record | Lower FPS or resolution scale |

## License

See [LICENSE](LICENSE) in this repository.
