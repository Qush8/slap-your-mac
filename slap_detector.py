#!/usr/bin/env python3
"""Play audio when a sharp mechanical impact is detected on the laptop.

Two backends:

1) IMU (macimu) — built-in SPU accelerometer on some Apple Silicon laptops (often M2+).
   Requires ``sudo``. Not available on many M1 / Intel / desktop Macs.

2) Microphone — loud transient from a slap/knock picked up by the built-in mic (or default
   input). Works on **most Macs**, including MacBook Pro M1 13-inch (2020); no sudo, but macOS will ask for microphone access the first time.
   Built-in speakers can re-trigger the mic while a clip plays; the script ignores mic hits until
   playback finishes (``afplay`` on macOS, threaded ``playsound`` elsewhere; use headphones if you
   still hear double-fires).

Run with ``--backend auto`` (default): use the built-in accelerometer when ``macimu`` detects it and
you run **with sudo**; if there is no sensor, **or** the sensor exists but you did not use sudo,
fall back to the microphone (same behavior as today on M1 / most machines).

Forced modes: ``--backend imu`` only sensor (will error without sudo); ``--backend mic`` only mic.

Privileged access (IMU):
    sudo /path/to/venv/bin/python slap_detector.py
    sudo /path/to/venv/bin/python slap_detector.py --backend imu

Sensitivity:
    IMU: tune ``--threshold`` (Δg between samples).
    Mic: tune ``--mic-threshold`` (0..1; **higher** = only **louder** taps/slaps trigger).

Default clips live in a per‑OS clip library folder (created on first run): on macOS
``~/Library/Application Support/SlapYourMac/sound/``; on Windows
``%LOCALAPPDATA%\\SlapYourMac\\sound\\``. Bundled samples copy there once; afterward add or delete
``.m4a`` / ``.mp3`` / ``.wav`` / … clips (no reinstall). Omit ``--sound`` to use that library.

The packaged bundle opens that folder in the file browser **once** on first macOS launch
(override ``--no-auto-folder``, or anytime ``--open-sounds-folder``). Windows: ``--open-sounds-folder``
opens Explorer.

Example::

    python slap_detector.py --sound ./sound/a.m4a ./sound/b.m4a

Background IMU example:
    sudo nohup …/python slap_detector.py --backend imu --sound ./one.m4a ./two.m4a >/tmp/slap.log 2>&1 &

Background mic (no sudo):
    nohup …/python slap_detector.py --backend mic --sound ./one.m4a ./two.m4a >/tmp/slap.log 2>&1 &

Also play when you plug the notebook back to wall power (battery → AC). macOS uses ``pmset``;
Windows uses ``psutil`` (install from requirements on Windows).

That mode on **macOS** **automatically turns off Apple's built-in charger ding** (PowerChime) so mostly your
clips play. Opt out with ``--keep-apple-power-chime``. For slap-detection-only use on Mac, mute the ding once
with ``--suppress-apple-power-chime`` without AC clip hooks::

    python slap_detector.py --sound-on-ac-connect

Windows::

    python slap_detector.py --backend mic --sound-on-ac-connect

Or on Mac, run ``defaults`` once to tweak PowerChime:

    defaults write com.apple.PowerChime ChimeOnNoHardware -bool true && killall PowerChime
"""

from __future__ import annotations

import argparse
import math
import os
import random
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from typing import Protocol


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _base_dir() -> str:
    """Repo root or PyInstaller extracted bundle folder (contains ``sound/`` when packaged)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if isinstance(meipass, str) and meipass:
            return meipass
        return os.path.dirname(sys.executable)
    return _SCRIPT_DIR


APP_NAME = "SlapYourMac"
SOUND_EXTENSIONS = (".m4a", ".mp3", ".wav", ".aiff", ".aif", ".caf")


def user_data_root() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
        return os.path.join(base, APP_NAME)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return os.path.join(local, APP_NAME)
        profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        return os.path.join(profile, "AppData", "Local", APP_NAME)
    xdg = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(xdg, APP_NAME)


def user_sound_library_dir() -> str:
    return os.path.join(user_data_root(), "sound")


def defaults_installed_marker_path() -> str:
    return os.path.join(user_data_root(), ".defaults_installed")


def auto_opened_sound_folder_marker_path() -> str:
    return os.path.join(user_data_root(), ".auto_opened_sound_folder")


def bundled_sound_dir() -> str:
    """Shipped samples next to script or inside PyInstaller bundle."""
    return os.path.join(_base_dir(), "sound")


def _is_known_audio_suffix(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in SOUND_EXTENSIONS)


def discover_audio_paths_in_folder(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    names = sorted(
        n for n in os.listdir(folder)
        if not n.startswith(".") and _is_known_audio_suffix(n)
    )
    return [os.path.join(folder, n) for n in names]


def _copy_bundled_samples_into_user_library() -> int:
    """Copy bundled clips into Application Support sound dir. Returns number of files copied."""
    bundled = bundled_sound_dir()
    if not os.path.isdir(bundled):
        return 0
    dst_dir = user_sound_library_dir()
    os.makedirs(dst_dir, exist_ok=True)
    copied = 0
    for name in sorted(os.listdir(bundled)):
        if name.startswith(".") or not _is_known_audio_suffix(name):
            continue
        src = os.path.join(bundled, name)
        if not os.path.isfile(src) or os.path.getsize(src) == 0:
            continue
        dst_path = os.path.join(dst_dir, name)
        if not os.path.isfile(dst_path):
            shutil.copy2(src, dst_path)
            copied += 1
    return copied


def resolve_library_sound_paths() -> list[str]:
    """
    Resolve clips under :func:`user_sound_library_dir` (per‑OS Application Support style path).

    - If clips are already there: use them (sorted).
    - If empty and bundled defaults never installed: copy bundled samples, create marker file.
    - If empty but marker exists: user removed everything — returns [] so main prints a hint.
    """
    lib_dir = user_sound_library_dir()
    os.makedirs(lib_dir, exist_ok=True)

    marker = defaults_installed_marker_path()
    paths = discover_audio_paths_in_folder(lib_dir)

    if paths:
        if not os.path.isfile(marker):
            try:
                with open(marker, "w", encoding="utf-8"):
                    pass
            except OSError:
                pass
        return sorted(paths)

    if not os.path.isfile(marker):
        _copy_bundled_samples_into_user_library()
        paths = discover_audio_paths_in_folder(lib_dir)
        if paths:
            try:
                with open(marker, "w", encoding="utf-8"):
                    pass
            except OSError:
                pass

    return sorted(paths)


def open_sound_library_folder() -> None:
    lib = user_sound_library_dir()
    os.makedirs(lib, exist_ok=True)
    if sys.platform == "darwin":
        opener = shutil.which("open")
        if opener:
            subprocess.run([opener, lib], check=False)
        else:
            print(lib, file=sys.stderr)
    elif sys.platform == "win32":
        try:
            os.startfile(lib)  # type: ignore[attr-defined]
        except OSError:
            subprocess.run(["explorer", os.path.normpath(lib)], check=False)
    else:
        xdg = shutil.which("xdg-open")
        if xdg:
            subprocess.run([xdg, lib], check=False)
        else:
            print(lib, file=sys.stderr)


def maybe_first_frozen_launch_open_sound_folder(args: argparse.Namespace) -> None:
    if args.no_auto_folder or args.sound is not None:
        return
    if not getattr(sys, "frozen", False):
        return
    if os.path.isfile(auto_opened_sound_folder_marker_path()):
        return
    open_sound_library_folder()
    try:
        with open(auto_opened_sound_folder_marker_path(), "w", encoding="utf-8"):
            pass
    except OSError:
        pass
    print("Opened sound library folder (first bundled launch only).")


CHARGING_POLL_SEC = 0.45


def _darwin_draws_ac_from_pmset(text: str) -> bool | None:
    """True if notebook reports drawing from mains, False from battery."""
    match = re.search(r"(?i)(?:Now )?drawing from '([^']+)'", text)
    if match is None:
        return None
    label = match.group(1).strip().lower()
    if "ac power" == label or label.startswith("ac "):
        return True
    if "battery power" == label or label.startswith("battery "):
        return False
    if label == "ac":
        return True
    return None


def _darwin_reads_ac_connected() -> bool | None:
    try:
        out = subprocess.run(
            ["/usr/bin/pmset", "-g", "batt"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        merged = (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return None
    return _darwin_draws_ac_from_pmset(merged)


def _win_reads_ac_via_psutil() -> bool | None:
    """True if Windows reports external power, False on battery, None if unknown."""
    try:
        import psutil
    except ImportError:
        return None
    batt = psutil.sensors_battery()
    if batt is None:
        return None
    plugged = batt.power_plugged
    if plugged is None:
        return None
    return bool(plugged)


def _reads_external_ac_power() -> bool | None:
    if sys.platform == "darwin":
        return _darwin_reads_ac_connected()
    if sys.platform == "win32":
        return _win_reads_ac_via_psutil()
    return None


def _notebook_ac_change_monitor(
    picker: SoundPicker,
    cooldown: float,
    stop_event: threading.Event,
) -> None:
    """Play on transition battery → mains; uses same picker/cooldown as slap detection."""
    last_plugged: bool | None = None
    last_fire = -cooldown
    warned = False

    while not stop_event.wait(CHARGING_POLL_SEC):
        current = _reads_external_ac_power()
        if current is None:
            if not warned:
                hint = ""
                if sys.platform == "darwin":
                    hint = (
                        "AC-connect sound disabled: pmset battery state unavailable "
                        "(desktop Mac or unexpected pmset output)."
                    )
                elif sys.platform == "win32":
                    hint = (
                        "AC-connect sound disabled: notebook battery/unplug signal unavailable "
                        "(desktop, VM, drivers, or install psutil: pip install -r requirements.txt)."
                    )
                else:
                    hint = (
                        "AC-connect hook is not implemented on this OS (--sound-on-ac-connect)."
                    )
                print(hint, file=sys.stderr)
                warned = True
            continue
        if last_plugged is False and current is True:
            now = time.monotonic()
            if (now - last_fire) >= cooldown:
                last_fire = now
                start_playback(picker.pick())
        last_plugged = current


def apply_darwin_suppress_apple_power_chime() -> bool:
    """
    Mutes macOS plug-in ding from ``PowerChime`` via ``defaults`` (persists).

    Undo: ``defaults write com.apple.PowerChime ChimeOnNoHardware -bool false && killall PowerChime``.
    """
    dc = shutil.which("defaults") or "/usr/bin/defaults"
    chk = subprocess.run(
        [dc, "read", "com.apple.PowerChime", "ChimeOnNoHardware"],
        capture_output=True,
        text=True,
    )
    prior_on = chk.returncode == 0 and chk.stdout.strip().lower() in (
        "1",
        "true",
        "yes",
    )

    if not prior_on:
        res = subprocess.run(
            [
                dc,
                "write",
                "com.apple.PowerChime",
                "ChimeOnNoHardware",
                "-bool",
                "true",
            ],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            msg = ((res.stderr or "") + (res.stdout or "")).strip() or f"exit {res.returncode}"
            print(f"Could not mute Apple charger chime: {msg}", file=sys.stderr)
            return False

    ks = shutil.which("killall")
    if ks:
        subprocess.run(
            [ks, "PowerChime"],
            capture_output=True,
            text=True,
        )
    if not prior_on:
        print(
            "Muted Apple charger ding (defaults com.apple.PowerChime → ChimeOnNoHardware=true).\n"
            "Undo: defaults write com.apple.PowerChime ChimeOnNoHardware -bool false\n"
            "     (restart PowerChime by unplugging AC or rebooting).\n"
        )
    return True


def delta_g(prev: tuple[float, float, float], cur: tuple[float, float, float]) -> float:
    dx = cur[0] - prev[0]
    dy = cur[1] - prev[1]
    dz = cur[2] - prev[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class PlaybackPollable(Protocol):
    def poll(self) -> int | None:
        ...


class _AfplayPlayback:
    __slots__ = ("_proc",)

    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc

    def poll(self) -> int | None:
        return self._proc.poll()


class _PlaysoundPlayback:
    __slots__ = ("_thread", "_exc")

    def __init__(self, sound_path: str) -> None:
        self._exc: BaseException | None = None

        def _run() -> None:
            try:
                from playsound import playsound

                playsound(sound_path, block=True)
            except BaseException as err:
                self._exc = err

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def poll(self) -> int | None:
        if self._thread.is_alive():
            return None
        return 1 if self._exc is not None else 0


def start_playback(sound_path: str) -> PlaybackPollable:
    """macOS: ``afplay`` subprocess. Else: ``playsound`` in a background thread."""
    if sys.platform == "darwin":
        exe = shutil.which("afplay")
        if exe is None:
            raise RuntimeError("afplay not found (required on macOS for playback)")
        proc = subprocess.Popen(
            [exe, sound_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return _AfplayPlayback(proc)
    return _PlaysoundPlayback(sound_path)


def playback_prereqs_ok() -> bool:
    """Validate external playback deps before blocking on ``main`` loops."""
    if sys.platform == "darwin":
        if shutil.which("afplay") is None:
            print("afplay not found (expected on macOS).", file=sys.stderr)
            return False
        return True
    try:
        import playsound  # noqa: F401
    except ImportError:
        print(
            "playsound required for playback on this OS. Install with:\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        return False
    return True


class SoundPicker:
    """Pick which clip to play when multiple ``--sound`` paths are configured."""

    __slots__ = ("_paths", "_alternate", "_index")

    def __init__(self, paths: list[str], alternate: bool) -> None:
        self._paths = paths
        self._alternate = alternate
        self._index = 0

    def pick(self) -> str:
        if len(self._paths) == 1:
            return self._paths[0]
        if self._alternate:
            path = self._paths[self._index % len(self._paths)]
            self._index += 1
            return path
        return random.choice(self._paths)


def imu_available() -> bool:
    try:
        from macimu import IMU
    except ImportError:
        return False
    return bool(IMU.available())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Play a sound when the laptop is slapped (notebook accelerometer on macOS, "
            "or microphone anywhere)."
        )
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "imu", "mic"],
        default="auto",
        help=(
            "auto: IMU when macimu sees a sensor and you run with sudo; "
            "otherwise mic (default: auto)"
        ),
    )
    parser.add_argument(
        "--sound",
        nargs="+",
        default=None,
        metavar="PATH",
        help=(
            "Override automatic clip library with explicit audio paths (.m4a, .wav, …). "
            "When omitted, clips load from macOS ~/Library/Application Support/"
            + APP_NAME
            + "/sound/ or Windows %%LOCALAPPDATA%%\\\\"
            + APP_NAME
            + "\\\\sound\\\\ — edit files there anytime."
        ),
    )
    parser.add_argument(
        "--alternate-sounds",
        action="store_true",
        help=(
            "With multiple --sound paths, rotate strictly A,B,A,... instead of picking randomly"
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.35,
        help="IMU: trigger when ‖Δaccel‖ exceeds this many g (default: 0.35)",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=0.5,
        help="Minimum seconds between triggers (default: 0.5)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=200,
        metavar="HZ",
        help="IMU sample rate in Hz (default: 200)",
    )
    parser.add_argument(
        "--mic-threshold",
        type=float,
        default=0.95,
        help=(
            "Mic: peak magnitude in (0,1] — higher = louder tap/slap needed "
            "(default: 0.95; lower ~0.68–0.85 if real slaps are missed)"
        ),
    )
    parser.add_argument(
        "--mic-rate",
        type=int,
        default=44100,
        metavar="HZ",
        help="Mic sample rate Hz (default: 44100)",
    )
    parser.add_argument(
        "--mic-block-ms",
        type=float,
        default=20.0,
        help="Mic read block length in ms (default: 20)",
    )
    parser.add_argument(
        "--open-sounds-folder",
        action="store_true",
        help="Ensure clip library exists, open it in the file browser, and exit (no detection).",
    )
    parser.add_argument(
        "--no-auto-folder",
        action="store_true",
        help=(
            "When running from a frozen executable, skip opening the clip folder on the first launch."
        ),
    )
    parser.add_argument(
        "--sound-on-ac-connect",
        action="store_true",
        dest="sound_on_ac_connect",
        help=(
            "Extra (notebook): also play clips when wall power reconnects (battery → AC). "
            "macOS: pmset. Windows: psutil battery. Same picker/cooldown as slap triggers. "
            "On macOS, automatically mutes Apple's charger ding unless --keep-apple-power-chime. "
            "Bundled SlapYourMac.app (frozen) enables this by default unless --no-sound-on-ac-connect."
        ),
    )
    parser.add_argument(
        "--no-sound-on-ac-connect",
        action="store_true",
        dest="no_sound_on_ac_connect",
        help=(
            "(macOS frozen .app mainly) Disable playing clips when AC reconnects "
            "(overrides bundled default)."
        ),
    )
    parser.add_argument(
        "--suppress-apple-power-chime",
        action="store_true",
        dest="suppress_apple_power_chime",
        help=(
            "(macOS) Mute Apple's built-in charger plug ding (PowerChime) via defaults. "
            "Use without --sound-on-ac-connect if you only want slap sounds but not AC hooks. "
            "With --sound-on-ac-connect this is redundant unless you used --keep-apple-power-chime."
        ),
    )
    parser.add_argument(
        "--keep-apple-power-chime",
        action="store_true",
        dest="keep_apple_power_chime",
        help=(
            "(macOS) With --sound-on-ac-connect, do not auto-mute Apple's charger ding."
        ),
    )
    args = parser.parse_args(argv)
    # PyInstaller bundle: charger hook on by default (Finder users rarely pass CLI flags).
    if getattr(args, "no_sound_on_ac_connect", False):
        args.sound_on_ac_connect = False
    elif getattr(sys, "frozen", False) and sys.platform == "darwin":
        args.sound_on_ac_connect = True
    return args


def run_imu(
    args: argparse.Namespace,
    sound_paths: list[str],
    picker: SoundPicker,
) -> int:
    try:
        from macimu import IMU
        from macimu import SensorNotFound
    except ImportError:
        print("macimu not installed; run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    if args.threshold <= 0:
        print("--threshold must be positive", file=sys.stderr)
        return 1

    if not IMU.available():
        print(
            "No SPU accelerometer on this Mac.\n"
            "Use:  --backend mic\n"
            "Or run on a notebook where macimu detects the sensor (see macimu docs).",
            file=sys.stderr,
        )
        return 1

    info = ""
    try:
        di = IMU.device_info()
        if di:
            info = f"\ndevice info: {di.get('product', di)}"
    except OSError:
        pass

    sound_mode = "alternate" if args.alternate_sounds else "random"
    listed = "\n".join(f"  {p}" for p in sound_paths)
    print(
        f"backend=imu  threshold={args.threshold:g} g  cooldown={args.cooldown:g} s  "
        f"sample_rate={args.sample_rate} Hz\n"
        f"sounds ({sound_mode}, {len(sound_paths)} file(s)):\n{listed}{info}\n"
        "Tip: raise --threshold if typing triggers; lower if misses slaps."
    )

    try:
        with IMU(accel=True, gyro=False, sample_rate=args.sample_rate) as imu:
            prev: tuple[float, float, float] | None = None
            last_trigger = -args.cooldown
            print("listening — IMU (Ctrl+C to stop)...")
            for sample in imu.stream_accel(interval=0.001):
                cur = (sample.x, sample.y, sample.z)
                if prev is None:
                    prev = cur
                    continue

                dg = delta_g(prev, cur)
                prev = cur

                now = time.monotonic()
                if dg > args.threshold and (now - last_trigger) >= args.cooldown:
                    last_trigger = now
                    start_playback(picker.pick())

    except PermissionError:
        print("Permission denied — IMU mode needs root. Example:\n", file=sys.stderr)
        print(f"  sudo {' '.join(sys.argv)}", file=sys.stderr)
        return 1
    except SensorNotFound as err:
        print(f"sensor error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nexiting...")
    return 0


def run_mic(
    args: argparse.Namespace,
    sound_paths: list[str],
    picker: SoundPicker,
) -> int:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print(
            "Mic mode needs numpy and sounddevice. Run:\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    if args.mic_threshold <= 0 or args.mic_threshold > 1:
        print("--mic-threshold must be in (0, 1]", file=sys.stderr)
        return 1

    if args.mic_rate <= 0:
        print("--mic-rate must be positive", file=sys.stderr)
        return 1

    block = max(128, int(args.mic_rate * (args.mic_block_ms / 1000.0)))

    sound_mode = "alternate" if args.alternate_sounds else "random"
    listed = "\n".join(f"  {p}" for p in sound_paths)
    if sys.platform == "darwin":
        mic_hint = (
            "Allow microphone access if macOS prompts. "
            "Raise --mic-threshold if ambient noise/typing triggers; lower if slaps are missed.\n"
        )
    elif sys.platform == "win32":
        mic_hint = (
            "Allow microphone access if Windows prompts (Settings → Privacy → Microphone). "
            "Raise --mic-threshold if ambient noise/typing triggers; lower if slaps are missed.\n"
        )
    else:
        mic_hint = (
            "Allow microphone access if your OS prompts. "
            "Raise --mic-threshold if ambient noise/typing triggers; lower if slaps are missed.\n"
        )

    print(
        f"backend=mic  mic_threshold={args.mic_threshold:g}  cooldown={args.cooldown:g} s  "
        f"mic_rate={args.mic_rate} Hz  block≈{block} samples\n"
        f"sounds ({sound_mode}, {len(sound_paths)} file(s)):\n{listed}\n"
        f"{mic_hint}"
        "While a clip is playing, mic triggers are ignored (avoids speaker→mic feedback loops)."
    )

    last_trigger = -args.cooldown
    playback: PlaybackPollable | None = None
    try:
        with sd.InputStream(
            samplerate=args.mic_rate,
            channels=1,
            dtype="float32",
            blocksize=block,
        ) as stream:
            print("listening — microphone (Ctrl+C to stop)...")
            while True:
                data, overflowed = stream.read(block)
                if overflowed:
                    pass
                samples = np.asarray(data, dtype=np.float32).reshape(-1)
                if samples.size == 0:
                    continue

                if playback is not None:
                    if playback.poll() is None:
                        continue
                    playback = None

                peak = float(np.max(np.abs(samples)))

                now = time.monotonic()
                if peak >= args.mic_threshold and (now - last_trigger) >= args.cooldown:
                    last_trigger = now
                    playback = start_playback(picker.pick())

    except OSError as err:
        msg = str(err).lower()
        if "permission" in msg or "audio" in msg:
            hint = ""
            if sys.platform == "darwin":
                hint = (
                    "On macOS: System Settings → Privacy & Security → Microphone "
                    "— enable Terminal / Python.\n"
                )
            elif sys.platform == "win32":
                hint = (
                    "On Windows: Settings → Privacy → Microphone — allow Python "
                    "(or SlapYourMac.exe if frozen).\n"
                )
            print(
                f"Microphone I/O error ({err}).\n"
                + hint,
                file=sys.stderr,
            )
        else:
            print(f"Microphone error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nexiting...")
    return 0


def resolve_backend(choice: str) -> str:
    if choice != "auto":
        return choice
    if imu_available():
        return "imu"
    return "mic"


def effective_detection_backend(args: argparse.Namespace) -> str:
    """IMU vs mic after ``--backend auto`` sudo rules; avoids ``UnboundLocalError`` on ``backend``."""
    resolved = resolve_backend(args.backend)
    if args.backend != "auto":
        return resolved

    if resolved == "imu":
        uid_fn = getattr(os, "geteuid", None)
        if callable(uid_fn) and uid_fn() != 0:
            print(
                "Built-in accelerometer detected, but IMU reads require root (sudo).\n"
                "Running without sudo — using microphone fallback.\n"
                "For sensor mode run the same command with sudo.\n"
            )
            return "mic"
        print("Accelerometer detected — using IMU backend.\n")
        return "imu"

    print(
        "No built-in accelerometer detected — using microphone fallback "
        "(grant mic access when asked).\n"
    )
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if hasattr(signal, "SIGCHLD"):
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    if args.open_sounds_folder:
        resolve_library_sound_paths()
        open_sound_library_folder()
        print(f"sound library folder:\n  {user_sound_library_dir()}\n")
        return 0

    if args.sound is not None:
        candidates = [os.path.abspath(os.path.expanduser(p)) for p in args.sound]
    else:
        candidates = resolve_library_sound_paths()
        if not candidates:
            print(
                "No usable audio clips found.\n"
                f"Put files here (extensions: {', '.join(SOUND_EXTENSIONS)}):\n"
                f"  {user_sound_library_dir()}\n"
                "Bundled demos copy themselves on first launch; if you removed everything, "
                "add clips or reset by deleting:\n"
                f"  {defaults_installed_marker_path()}\n"
                "and the clips in that folder, then launch once to re-copy samples.\n"
                "Alternatively pass explicit paths after --sound.\n",
                file=sys.stderr,
            )
            return 1

    sound_paths: list[str] = []
    for sound_abs in candidates:
        if not os.path.isfile(sound_abs):
            print(f"sound file not found: {sound_abs}", file=sys.stderr)
            return 1
        if os.path.getsize(sound_abs) == 0:
            print(
                f"sound file is empty (not a valid audio clip): {sound_abs}",
                file=sys.stderr,
            )
            return 1
        sound_paths.append(sound_abs)

    picker = SoundPicker(sound_paths, args.alternate_sounds)

    if args.backend == "imu" and sys.platform != "darwin":
        print(
            "--backend imu only works on macOS (macimu / built-in notebook accelerometer).\n"
            "On this system use:  python slap_detector.py --backend mic",
            file=sys.stderr,
        )
        return 1

    if args.sound_on_ac_connect and sys.platform == "win32":
        try:
            import psutil  # noqa: F401
        except ImportError:
            print(
                "--sound-on-ac-connect on Windows requires psutil. Install with:\n"
                "  pip install -r requirements.txt",
                file=sys.stderr,
            )
            return 1

    if args.suppress_apple_power_chime and sys.platform != "darwin":
        print(
            "--suppress-apple-power-chime works only on macOS.",
            file=sys.stderr,
        )
        return 1

    if not playback_prereqs_ok():
        return 1

    mute_apple_explicit = args.suppress_apple_power_chime
    mute_apple_auto_ac = (
        args.sound_on_ac_connect and not getattr(args, "keep_apple_power_chime", False)
    )
    if sys.platform == "darwin" and (mute_apple_explicit or mute_apple_auto_ac):
        if not apply_darwin_suppress_apple_power_chime():
            return 1

    chosen_backend = effective_detection_backend(args)

    if args.sound is None:
        print(
            "sound library folder (add/remove .m4a, .mp3, … clips anytime):\n"
            f"  {user_sound_library_dir()}\n"
        )
        maybe_first_frozen_launch_open_sound_folder(args)

    hook_stop = threading.Event()
    if args.sound_on_ac_connect:
        print(
            "Also playing when notebook AC power reconnects (--sound-on-ac-connect).\n"
        )
        threading.Thread(
            target=_notebook_ac_change_monitor,
            args=(picker, args.cooldown, hook_stop),
            daemon=True,
            name="NotebookACConnect",
        ).start()

    try:
        if chosen_backend == "imu":
            return run_imu(args, sound_paths, picker)
        return run_mic(args, sound_paths, picker)
    finally:
        hook_stop.set()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
