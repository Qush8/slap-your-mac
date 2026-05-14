# SlapYourMac

Play bundled sounds when the laptop is tapped. Uses the built-in accelerometer when available (`macimu`, requires `sudo`), otherwise the microphone.

## Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python slap_detector.py
```

## Sound clips (no rebuild needed)

Tracks are loaded from **`~/Library/Application Support/SlapYourMac/sound/`** (created on first launch).

1. Run the app **once** — bundled demo clips are copied there if the folder is empty.
2. Add or delete **`.m4a`**, **`.mp3`**, **`.wav`**, **`.aiff`**, **`.aif`**, or **`.caf`** files and **restart** the app.
3. To get the bundled demos again after removing everything: delete  
   **`~/Library/Application Support/SlapYourMac/.defaults_installed`**  
   and clear clips in `sound/` (or remove the clips only and add your own), then launch once with an empty library to re-seed.

Override with explicit paths: `python slap_detector.py --sound /path/a.m4a /path/b.m4a`

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

ქართულად მოკლედ: წყაროდან ან **`dist/SlapYourMac.app`** ორმაგი წკაპით; მიკროფონზე ნებართვა macOS დიალოგით; შესვლაზე ავტოსტარტისთვის გამოიყენე `extras/` plist მაგალითი.
