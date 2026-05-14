# SlapYourMac

Play sounds when the laptop is tapped — **accelerometer mode on compatible macOS notebooks** (`macimu`, typically needs `sudo`) or **microphone mode** (works on macOS **and Windows**).

## Run from source (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python slap_detector.py
```

macOS skips the **`playsound`** wheel (playback uses **`afplay`**). That avoids install failures on very new Python (e.g. 3.14) where `playsound` often does not build.

On a **notebook Mac**, you can **also** play the same clips when you plug in wall power (battery → mains):

```bash
python slap_detector.py --sound-on-ac-connect
```

This **automatically mutes Apple's built-in charger ding** (PowerChime via `defaults`) so you mainly hear SlapYourMac. **Persisted**: you only see the explanatory message once; later launches stay quiet unless you revert below. Same **`--alternate-sounds`**, **`--cooldown`**, and clip-library rules as slap triggers.

Keep Apple's ding alongside your clips:

```bash
python slap_detector.py --sound-on-ac-connect --keep-apple-power-chime
```

Mute Apple's ding **without** AC clip playback (mic/IMU only):

```bash
python slap_detector.py --suppress-apple-power-chime
```

Uses **`pmset -g batt`** for AC detection; desktops without notebook battery logging may skip hooks. Undo Apple ding only:

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

Reveal the clip folder in Explorer anytime:

```powershell
python slap_detector.py --open-sounds-folder
```

## Freeze for Windows (.exe folder)

Run on Windows from the repo root:

```powershell
pip install -r requirements.txt -r requirements-build.txt
pyinstaller slap-your-mac-win.spec
```

Output folder: **`dist/SlapYourMac/`** with **`SlapYourMac.exe`**. Zip the whole **`dist/SlapYourMac`** folder (not only the exe) so DLLs and resources ship together.

**Verify** `SlapYourMac.exe`, mic access, and audio formats on actual Windows PCs.

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

ქართულად მოკლედ: macOS‑ზე **`dist/SlapYourMac.app`** კონტექტი ზემოთ; Windows‑ზე მიკროფონზე **`python slap_detector.py --backend mic`**; მიკროფონზე ნებართვა OS დიალოგით; შესვლაზე macOS‑ისთვის გამოიყენე `extras/` plist მაგალითი.
