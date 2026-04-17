"""Utility functions and constants for YTDown."""

import re
import os
import time

# ─── HTTP Headers ─────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    # Bypass EU consent / cookie consent
    "Cookie": "SOCS=CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjUwNDE1LjA1X3AwGgJlbiACGgYIgJb5vAY",
}

# ─── ITAG Quality Map ─────────────────────────────────────────────────────────
# Reference: https://gist.github.com/AgentOak/34d47c65b1d28829bb17c24c04a0096

ITAG_MAP = {
    # Muxed (video + audio)
    18:  {"quality": "360p",  "type": "muxed",  "ext": "mp4",  "codec": "avc1/mp4a"},
    22:  {"quality": "720p",  "type": "muxed",  "ext": "mp4",  "codec": "avc1/mp4a"},
    37:  {"quality": "1080p", "type": "muxed",  "ext": "mp4",  "codec": "avc1/mp4a"},
    38:  {"quality": "3072p", "type": "muxed",  "ext": "mp4",  "codec": "avc1/mp4a"},
    43:  {"quality": "360p",  "type": "muxed",  "ext": "webm", "codec": "vp8/vorbis"},
    44:  {"quality": "480p",  "type": "muxed",  "ext": "webm", "codec": "vp8/vorbis"},
    45:  {"quality": "720p",  "type": "muxed",  "ext": "webm", "codec": "vp8/vorbis"},
    # Video only (adaptive)
    137: {"quality": "1080p", "type": "video",  "ext": "mp4",  "codec": "avc1"},
    248: {"quality": "1080p", "type": "video",  "ext": "webm", "codec": "vp9"},
    136: {"quality": "720p",  "type": "video",  "ext": "mp4",  "codec": "avc1"},
    247: {"quality": "720p",  "type": "video",  "ext": "webm", "codec": "vp9"},
    135: {"quality": "480p",  "type": "video",  "ext": "mp4",  "codec": "avc1"},
    244: {"quality": "480p",  "type": "video",  "ext": "webm", "codec": "vp9"},
    134: {"quality": "360p",  "type": "video",  "ext": "mp4",  "codec": "avc1"},
    243: {"quality": "360p",  "type": "video",  "ext": "webm", "codec": "vp9"},
    133: {"quality": "240p",  "type": "video",  "ext": "mp4",  "codec": "avc1"},
    242: {"quality": "240p",  "type": "video",  "ext": "webm", "codec": "vp9"},
    160: {"quality": "144p",  "type": "video",  "ext": "mp4",  "codec": "avc1"},
    278: {"quality": "144p",  "type": "video",  "ext": "webm", "codec": "vp9"},
    # High quality video (adaptive)
    271: {"quality": "1440p", "type": "video",  "ext": "webm", "codec": "vp9"},
    264: {"quality": "1440p", "type": "video",  "ext": "mp4",  "codec": "avc1"},
    272: {"quality": "4320p", "type": "video",  "ext": "webm", "codec": "vp9"},
    313: {"quality": "2160p", "type": "video",  "ext": "webm", "codec": "vp9"},
    401: {"quality": "2160p", "type": "video",  "ext": "mp4",  "codec": "av01"},
    400: {"quality": "1440p", "type": "video",  "ext": "mp4",  "codec": "av01"},
    # Audio only (adaptive)
    140: {"quality": "128kbps", "type": "audio", "ext": "m4a",  "codec": "mp4a"},
    141: {"quality": "256kbps", "type": "audio", "ext": "m4a",  "codec": "mp4a"},
    251: {"quality": "160kbps", "type": "audio", "ext": "webm", "codec": "opus"},
    250: {"quality": "70kbps",  "type": "audio", "ext": "webm", "codec": "opus"},
    249: {"quality": "50kbps",  "type": "audio", "ext": "webm", "codec": "opus"},
    139: {"quality": "48kbps",  "type": "audio", "ext": "m4a",  "codec": "mp4a"},
}

# Quality ordering for sorting (lower index = higher quality)
QUALITY_ORDER = [
    "4320p", "2160p", "1440p", "1080p", "720p",
    "480p", "360p", "240p", "144p",
    "256kbps", "160kbps", "128kbps", "70kbps", "50kbps", "48kbps",
]


# ─── String Helpers ───────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:200]  # Limit length


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
        r"^([A-Za-z0-9_-]{11})$",  # Raw video ID
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
