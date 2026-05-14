# SlapYourMac

Play sounds when the laptop is tapped — **accelerometer mode on compatible macOS notebooks** (`macimu`, typically needs `sudo`) or **microphone mode** (works on macOS **and Windows**).

## Who runs what?

| Scenario | Goal | Typical steps |
|---------|------|----------------|
| **End user** (frozen app) | No Python tools | Receive **`SlapYourMac.app`** (macOS) or a **zip** of **`dist/SlapYourMac`** (Windows). First run: microphone permission when asked; bundled clips live in app support folders (see below). |
| **Developer** (build locally) | Reproducible venv + PyInstaller | macOS: **`scripts/build_mac_app.sh`**; Windows: **`scripts/setup_and_build_windows.ps1`**. |

**Silent “Next–Next installer” installers** (MSI, Inno Setup, signed macOS `.pkg`) are **not part of this repo by default**. They’re possible as a separate packaging step later (including codesign/notarization on Mac).

### Download frozen Windows zip (without Git clone)

The repo stays **without** bulky zips in git history — instead **GitHub Actions** builds a real Windows package on Microsoft’s runners:

1. Open your repo → **Actions** → workflow **Build Windows zip** → **Run workflow** (manual run), or push a Git tag **`v1.0.0`** etc. so the workflow **also attaches** `SlapYourMac-windows.zip` to a **GitHub Release** (permalink for friends — WeTransfer‑style „one stable link”).
2. When the job finishes, open **Build Windows zip → latest run → Artifacts** and download **`SlapYourMac-windows.zip`**, or grab it from **Releases** if you tagged.
3. Recipients unzip, open **`SlapYourMac/SlapYourMac.exe`** (whole folder stays together).

## Run from source (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python slap_detector.py
```

macOS skips the **`playsound`** wheel (playback uses **`afplay`**). That avoids install failures on very new Python (e.g. 3.14) where `playsound` often does not build.

On a **notebook Mac**, you can **also** play the same clips when you plug in wall power (battery → mains). Detection uses **`pmset -g batt`**. **`--suppress-apple-power-chime`**, **`--keep-apple-power-chime`**, and **PowerChime** muting apply **only on macOS**.

```bash
python slap_detector.py --sound-on-ac-connect
```

With `--sound-on-ac-connect`, SlapYourMac **automatically mutes Apple's built-in charger ding** (PowerChime via `defaults`) so you mainly hear SlapYourMac. **Persisted**: you only see the explanatory message once; later launches stay quiet unless you revert below. Same **`--alternate-sounds`**, **`--cooldown`**, and clip-library rules as slap triggers.

Keep Apple's ding alongside your clips:

```bash
python slap_detector.py --sound-on-ac-connect --keep-apple-power-chime
```

Mute Apple's ding **without** AC clip playback (mic/IMU only):

```bash
python slap_detector.py --suppress-apple-power-chime
```

Desktops without notebook battery logging may not get AC transitions. Undo Apple ding only:

```bash
defaults write com.apple.PowerChime ChimeOnNoHardware -bool false
```

## Run from source (Windows, microphone only)

Use **Python 3.10–3.13** when possible (easier installs for playback dependencies).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python slap_detector.py --backend mic
```

Grant **microphone** access when prompted. The script uses Windows’ **default recording device** — select the built‑in mic or a USB headset in **Settings → System → Sound → Input**.

Playback on Windows goes through **`playsound`** (often fine for `.mp3`/`.wav`). If `.m4a` fails or stutters, try `.mp3` or `.wav` clips instead.

### Charger connect sound (battery → AC) on Windows

On a **notebook that reports battery state**, **`--sound-on-ac-connect`** plays the **same rotating clip library** when you plug in mains. **`psutil`** reads `power_plugged`; `pip install -r requirements.txt` installs it **on Windows**. There is **no built-in equivalent** here to mute Windows generic connect tones like macOS PowerChime.

VMs, some desktops/tablets without a battery sensor, or odd drivers may not expose unplug/plug state; if so you see **one** hint on stderr.

```powershell
python slap_detector.py --backend mic --sound-on-ac-connect
```

Reveal the clip folder in Explorer anytime:

```powershell
python slap_detector.py --open-sounds-folder
```

## Freeze for Windows (.exe folder)

**One-shot** from the cloned repo (creates `.venv`, installs deps, runs PyInstaller):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_and_build_windows.ps1
```

Output: **`dist/SlapYourMac/`** with **`SlapYourMac.exe`**. Zip the whole **`dist/SlapYourMac`** folder (not only the exe) so DLLs and resources ship together.

Minimal manual variant from repo root:

```powershell
pip install -r requirements.txt -r requirements-build.txt
pyinstaller slap-your-mac-win.spec
```

**Verify** `SlapYourMac.exe`, mic access, and audio formats on actual Windows PCs. For AC-connect sounds, test unplug/plug on **real notebook hardware**.

## Sound clips (no rebuild needed)

On **macOS**, tracks load from **`~/Library/Application Support/SlapYourMac/sound/`** (created on first launch).  
On **Windows**, from **`%LOCALAPPDATA%\SlapYourMac\sound\`** (e.g. `C:\Users\You\AppData\Local\SlapYourMac\sound\`).

1. Run the app **once** — bundled demo clips are copied there if the folder is empty.
2. Add or delete **`.m4a`**, **`.mp3`**, **`.wav`**, **`.aiff`**, **`.aif`**, or **`.caf`** files and **restart** the app.
3. To get the bundled demos again after removing everything: delete the marker **`SlapYourMac/.defaults_installed`** under your clips root (paths above), clear clips in `sound/`, then launch once with an empty library to re-seed.

Override with explicit paths: `python slap_detector.py --sound /path/a.m4a /path/b.m4a`

**Open** the clip folder easily — run `python slap_detector.py --open-sounds-folder` (seeds demos if empty).

The bundled **macOS `.app`** (or frozen **Windows `.exe`**) opens that clip folder automatically **once** on first launch; use `--no-auto-folder` when launching from a shell to skip it.

## Build the macOS app (double‑click, no Terminal)

Requires Xcode Command Line Tools for code signing hints (PyInstaller still builds without your own signing).

```bash
chmod +x scripts/build_mac_app.sh
./scripts/build_mac_app.sh
```

If **`.venv`** is missing, the script creates **`python3`** (`PYTHON=/path/to/python3` overrides), installs **`requirements.txt`** and **`requirements-build.txt`**, then builds.

Output: **`dist/SlapYourMac.app`**. Copy to **Applications**, double‑click to run.

PyInstaller may warn about **codesign** (“resource fork…”): the `.app` often still runs — **right‑click → Open** the first time. To strip Finder metadata before sharing: `xattr -cr dist/SlapYourMac.app`, then retry signing if you use Apple Developer ID.

- First launch: macOS asks for **microphone** access — allow **SlapYourMac**.
- Unknown developer: **System Settings → Privacy & Security → Open Anyway** after first block, or right‑click → Open.

### Share / upload

Zip the app:

```bash
cd dist && zip -ry ../SlapYourMac.app.zip SlapYourMac.app
```

Recipients unzip and move `SlapYourMac.app` to Applications.

### “SlapYourMac is damaged and can’t be opened”

Usually **Gatekeeper / quarantine**, not a corrupted download. On the recipient’s Mac run:

```bash
xattr -cr /Applications/SlapYourMac.app
```

(Adjust the path if the app is elsewhere.) Or **right‑click the app → Open → Open**, and check **System Settings → Privacy & Security → Open Anyway**.

## Start at login (optional)

See [`extras/com.slapyourmac.launchagent.plist.example`](extras/com.slapyourmac.launchagent.plist.example): copy to `~/Library/LaunchAgents/`, fix the app path, then `launchctl load`.

## Quit

Dock → **SlapYourMac** → **Quit** (Cmd+Q).

---

ქართულად მოკლედ: მომხმარებელი იღებს **zip / .app ან სრულ `dist/SlapYourMac`** — Python არ სჭირდება; დეველოპერი **`scripts/build_mac_app.sh`** (მაკი), **`scripts/setup_and_build_windows.ps1`** (Windows). მაკზე **PowerChime** უხმო იკონტროლება; Windows AC კლიპი **psutil** გამოითვლება — რეალ ლეპტოპზე გამოსაცდელია. შესვლაზე macOS‑ისთვის — `extras/` plist მაგალითი.
