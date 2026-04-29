"""
FFmpeg detection, video+audio merge, and audio extraction.

Phase 2: Enables 1080p/4K download by merging separate video and audio streams.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

# ─── FFmpeg Detection ─────────────────────────────────────────────────────────

_ffmpeg_path_cache: Optional[str] = None  # None = not yet checked, "" = not found


def find_ffmpeg() -> Optional[str]:
    """
    Find ffmpeg executable on this system.

    Checks PATH first, then common installation locations.
    Returns the full path, or None if not found.
    """
    global _ffmpeg_path_cache
    if _ffmpeg_path_cache is not None:
        return _ffmpeg_path_cache or None

    # shutil.which searches PATH
    found = shutil.which("ffmpeg")
    if found:
        _ffmpeg_path_cache = found
        return found

    # Common manual installation paths on Windows
    local_app   = os.environ.get("LOCALAPPDATA", "")
    app_data    = os.environ.get("APPDATA", "")
    user_home   = os.path.expanduser("~")
    windows_paths = [
        # Manual install
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        # Scoop
        os.path.join(user_home, "scoop", "shims", "ffmpeg.exe"),
        os.path.join(user_home, "scoop", "apps", "ffmpeg", "current", "bin", "ffmpeg.exe"),
        # Chocolatey
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg\bin\ffmpeg.exe",
        # LocalAppData / AppData
        os.path.join(local_app, "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(app_data, "ffmpeg", "bin", "ffmpeg.exe"),
        # Downloads or Desktop (manual unzip)
        os.path.join(user_home, "Downloads", "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(user_home, "ffmpeg", "bin", "ffmpeg.exe"),
        # winget default path
        r"C:\Program Files\FFmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\FFmpeg for Audacity\bin\ffmpeg.exe",
    ]
    # Common paths on Linux/macOS
    unix_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/opt/local/bin/ffmpeg",
    ]

    if sys.platform == "win32":
        # WinGet install path (Gyan.FFmpeg) — PATH not updated until shell restart
        winget_base = os.path.join(local_app, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_base):
            for pkg_dir in os.listdir(winget_base):
                if pkg_dir.startswith("Gyan.FFmpeg"):
                    candidate = os.path.join(winget_base, pkg_dir)
                    # Walk one level deeper to find bin/ffmpeg.exe
                    for sub in os.listdir(candidate):
                        fp = os.path.join(candidate, sub, "bin", "ffmpeg.exe")
                        if os.path.isfile(fp):
                            _ffmpeg_path_cache = fp
                            return fp

    for path in (windows_paths if sys.platform == "win32" else unix_paths):
        if os.path.isfile(path):
            _ffmpeg_path_cache = path
            return path

    _ffmpeg_path_cache = ""
    return None


def get_ffmpeg_version() -> Optional[str]:
    """Return ffmpeg version string, or None if not available."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r"ffmpeg version ([\S]+)", result.stdout)
        return m.group(1) if m else "unknown"
    except Exception:
        return None


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on this system."""
    return find_ffmpeg() is not None


# ─── Merge Helpers ────────────────────────────────────────────────────────────

def _run_ffmpeg(args: list[str], label: str = "Processing") -> None:
    """
    Run ffmpeg with given arguments.

    Shows a simple spinner for operations without known duration.

    Raises:
        RuntimeError: If ffmpeg exits with non-zero code.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg not found. Install FFmpeg to merge video+audio.\n"
            "  Windows: https://ffmpeg.org/download.html\n"
            "  Or: winget install ffmpeg"
        )

    cmd = [ffmpeg, "-y"] + args  # -y = overwrite output without asking

    print(f"  -> {label}...", end="", flush=True)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        # Extract meaningful error from stderr
        stderr_lines = proc.stderr.strip().splitlines()
        error_line = next(
            (l for l in reversed(stderr_lines) if "Error" in l or "Invalid" in l or "No such" in l),
            stderr_lines[-1] if stderr_lines else "Unknown error",
        )
        raise RuntimeError(f"FFmpeg failed: {error_line}")

    print(" done")


# ─── Public API ───────────────────────────────────────────────────────────────

def merge_video_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    remove_sources: bool = True,
) -> str:
    """
    Merge a video-only file and an audio-only file into a single mp4.

    Uses stream copy (no re-encoding) for maximum speed and quality.

    Args:
        video_path: Path to the video-only file.
        audio_path: Path to the audio-only file.
        output_path: Path for the merged output file.
        remove_sources: Delete video_path and audio_path after successful merge.

    Returns:
        Absolute path of the merged output file.
    """
    _run_ffmpeg(
        [
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",   # No re-encode
            "-c:a", "copy",
            "-movflags", "+faststart",  # Web-optimized MP4
            output_path,
        ],
        label="Merging video + audio",
    )

    if remove_sources:
        for path in (video_path, audio_path):
            try:
                os.remove(path)
            except OSError:
                pass

    return os.path.abspath(output_path)


def extract_audio_as_mp3(
    input_path: str,
    output_path: str,
    bitrate: str = "192k",
    remove_source: bool = False,
) -> str:
    """
    Convert an audio stream file to MP3.

    Args:
        input_path: Source audio file (m4a, webm, etc.)
        output_path: Output MP3 file path.
        bitrate: MP3 bitrate (default 192k).
        remove_source: Delete input_path after conversion.

    Returns:
        Absolute path of the MP3 file.
    """
    _run_ffmpeg(
        [
            "-i", input_path,
            "-vn",                    # No video
            "-acodec", "libmp3lame",
            "-ab", bitrate,
            "-ar", "44100",
            output_path,
        ],
        label=f"Converting to MP3 ({bitrate})",
    )

    if remove_source:
        try:
            os.remove(input_path)
        except OSError:
            pass

    return os.path.abspath(output_path)


def extract_audio_copy(
    input_path: str,
    output_path: str,
    remove_source: bool = False,
) -> str:
    """
    Copy the audio stream from a file without re-encoding.

    Args:
        input_path: Source file (mp4, webm, m4a…).
        output_path: Output file (must match codec, e.g. .m4a for mp4a).
        remove_source: Delete input_path after extraction.

    Returns:
        Absolute path of the extracted audio file.
    """
    _run_ffmpeg(
        [
            "-i", input_path,
            "-vn",
            "-acodec", "copy",
            output_path,
        ],
        label="Extracting audio",
    )

    if remove_source:
        try:
            os.remove(input_path)
        except OSError:
            pass

    return os.path.abspath(output_path)
