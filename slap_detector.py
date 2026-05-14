#!/usr/bin/env python3
"""Play audio when a sharp mechanical impact is detected on the laptop.

Two backends:

1) IMU (macimu) — built-in SPU accelerometer on some Apple Silicon laptops (often M2+).
   Requires ``sudo``. Not available on many M1 / Intel / desktop Macs.

2) Microphone — loud transient from a slap/knock picked up by the built-in mic (or default
   input). Works on **most Macs**, including MacBook Pro M1 13-inch (2020); no sudo, but macOS will ask for microphone access the first time.
   Built-in speakers can re-trigger the mic while a clip plays; the script ignores mic hits until
   ``afplay`` finishes (use headphones if you still hear double-fires).

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

Default clips live under ``~/Library/Application Support/SlapYourMac/sound/``. On first run the
bundled samples are copied there; afterward add or delete ``.m4a`` / ``.mp3`` / ``.wav`` / … files
in that folder (no reinstall). Omit ``--sound`` to use that library; pass ``--sound`` paths to override.

Example::

    python slap_detector.py --sound ./sound/a.m4a ./sound/b.m4a

Background IMU example:
    sudo nohup …/python slap_detector.py --backend imu --sound ./one.m4a ./two.m4a >/tmp/slap.log 2>&1 &

Background mic (no sudo):
    nohup …/python slap_detector.py --backend mic --sound ./one.m4a ./two.m4a >/tmp/slap.log 2>&1 &
"""

from __future__ import annotations

import argparse
import math
import os
import random
import signal
import shutil
import subprocess
import sys
import time


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
    base = os.path.expanduser("~/Library/Application Support")
    return os.path.join(base, APP_NAME)


def user_sound_library_dir() -> str:
    return os.path.join(user_data_root(), "sound")


def defaults_installed_marker_path() -> str:
    return os.path.join(user_data_root(), ".defaults_installed")


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
    Use ``~/Library/Application Support/SlapYourMac/sound/``.

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


def delta_g(prev: tuple[float, float, float], cur: tuple[float, float, float]) -> float:
    dx = cur[0] - prev[0]
    dy = cur[1] - prev[1]
    dz = cur[2] - prev[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def trigger_play(sound_path: str, afplay: str) -> subprocess.Popen:
    """Decode/play via macOS ``afplay`` — supports common formats including ``.m4a``, ``.mp3``, ``.caf``, ``.aiff``, ``.wav``."""
    return subprocess.Popen(
        [afplay, sound_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


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
        description="Play a sound when the laptop is slapped (accelerometer or microphone)."
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
            "Override automatic library with explicit paths (macOS afplay formats). "
            "When omitted, sounds are loaded from ~/Library/Application Support/"
            + APP_NAME
            + "/sound/ — add or remove clips there."
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
    return parser.parse_args(argv)


def run_imu(
    args: argparse.Namespace,
    sound_paths: list[str],
    picker: SoundPicker,
    afplay: str,
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
                    trigger_play(picker.pick(), afplay)

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
    afplay: str,
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
    print(
        f"backend=mic  mic_threshold={args.mic_threshold:g}  cooldown={args.cooldown:g} s  "
        f"mic_rate={args.mic_rate} Hz  block≈{block} samples\n"
        f"sounds ({sound_mode}, {len(sound_paths)} file(s)):\n{listed}\n"
        "Allow microphone access if macOS prompts. "
        "Raise --mic-threshold if ambient noise/typing triggers; lower if slaps are missed.\n"
        "While a clip is playing, mic triggers are ignored (avoids speaker→mic feedback loops)."
    )

    last_trigger = -args.cooldown
    playback_proc: subprocess.Popen | None = None
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

                if playback_proc is not None:
                    if playback_proc.poll() is None:
                        continue
                    playback_proc = None

                peak = float(np.max(np.abs(samples)))

                now = time.monotonic()
                if peak >= args.mic_threshold and (now - last_trigger) >= args.cooldown:
                    last_trigger = now
                    playback_proc = trigger_play(picker.pick(), afplay)

    except OSError as err:
        msg = str(err).lower()
        if "permission" in msg or "audio" in msg:
            print(
                f"Microphone I/O error ({err}).\n"
                "On macOS: System Settings → Privacy & Security → Microphone — enable Terminal / Python.",
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if hasattr(signal, "SIGCHLD"):
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

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

    afplay = shutil.which("afplay")
    if afplay is None:
        print("afplay not found (expected on macOS).", file=sys.stderr)
        return 1

    backend = resolve_backend(args.backend)
    if args.backend == "auto":
        if backend == "imu":
            if os.geteuid() != 0:
                print(
                    "Built-in accelerometer detected, but IMU reads require root (sudo).\n"
                    "Running without sudo — using microphone fallback.\n"
                    "For sensor mode run the same command with sudo.\n"
                )
                backend = "mic"
            else:
                print("Accelerometer detected — using IMU backend.\n")
        else:
            print(
                "No built-in accelerometer detected — using microphone fallback "
                "(grant mic access when asked).\n"
            )

    if args.sound is None:
        print(
            "sound library folder (add/remove .m4a, .mp3, … clips anytime):\n"
            f"  {user_sound_library_dir()}\n"
        )

    if backend == "imu":
        return run_imu(args, sound_paths, picker, afplay)
    return run_mic(args, sound_paths, picker, afplay)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
