"""Utility functions and constants for YTDown."""

import os
import re


# ─── Quality Ordering ─────────────────────────────────────────────────────────

QUALITY_ORDER = [
    "4320p", "2160p", "1440p", "1080p", "720p",
    "480p", "360p", "240p", "144p",
    "256kbps", "160kbps", "128kbps", "70kbps", "50kbps", "48kbps",
]


# ─── HTTP Headers ───────────────────────────────────────────────────────────

def get_browser_headers() -> dict:
    """Return headers mimicking a real Chrome browser."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "*/*"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json",
        "Origin": "https://www.youtube.com",
        "Referer": "https://www.youtube.com/",
    }


# ─── String Helpers ───────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:200]


def format_bytes(size: int) -> str:
    """Convert bytes to human-readable string."""
    if size <= 0:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_duration(seconds: int) -> str:
    """Convert seconds to MM:SS or HH:MM:SS."""
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_speed(bps: float) -> str:
    """Convert bytes/sec to human-readable speed."""
    return f"{format_bytes(int(bps))}/s"


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def quality_sort_key(quality: str) -> int:
    """Return sort index for quality string (lower = higher quality)."""
    try:
        return QUALITY_ORDER.index(quality)
    except ValueError:
        return 999


def ensure_dir(path: str) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)
