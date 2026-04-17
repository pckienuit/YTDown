"""Chunked downloader with progress reporting."""

import os
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from core.utils import HEADERS, ensure_dir, format_bytes, format_speed, sanitize_filename

# ─── Types ────────────────────────────────────────────────────────────────────

ProgressCallback = Callable[[int, int, float], None]
# Args: (downloaded_bytes, total_bytes, speed_bps)

CHUNK_SIZE = 8192       # 8 KB chunks
MAX_RETRIES = 3
RETRY_DELAY = 2.0       # seconds


# ─── Progress Helpers ─────────────────────────────────────────────────────────

def _make_progress_bar(downloaded: int, total: int, width: int = 30) -> str:
    """Render ASCII progress bar."""
    if total <= 0:
        filled = 0
        pct = 0.0
    else:
        ratio = min(downloaded / total, 1.0)
        filled = int(width * ratio)
        pct = ratio * 100

    bar = "█" * filled + "░" * (width - filled)
    dl_str = format_bytes(downloaded)
    tot_str = format_bytes(total) if total > 0 else "?"
    return f"[{bar}] {pct:5.1f}% | {dl_str} / {tot_str}"


def _console_progress(downloaded: int, total: int, speed: float) -> None:
    """Default console progress callback."""
    bar = _make_progress_bar(downloaded, total)
    speed_str = format_speed(speed)
    if total > 0 and speed > 0:
        eta_s = (total - downloaded) / speed
        h, r = divmod(int(eta_s), 3600)
        m, s = divmod(r, 60)
        eta_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        print(f"\r  {bar} | {speed_str} | ETA {eta_str} ", end="", flush=True)
    else:
        print(f"\r  {bar} | {speed_str}        ", end="", flush=True)


# ─── Core Downloader ──────────────────────────────────────────────────────────

def download_url(
    url: str,
    output_path: str,
    callback: Optional[ProgressCallback] = None,
    resume: bool = True,
) -> str:
    """
    Download a URL to output_path with progress and retry.

    Args:
        url: Direct download URL.
        output_path: Full path to save file.
        callback: Progress callback (downloaded, total, speed_bps).
        resume: Attempt HTTP range resume if file partially exists.

    Returns:
        Absolute path of downloaded file.
    """
    if callback is None:
        callback = _console_progress

    existing_size = 0
    if resume and os.path.exists(output_path):
        existing_size = os.path.getsize(output_path)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = dict(HEADERS)
            if existing_size > 0:
                headers["Range"] = f"bytes={existing_size}-"

            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as resp:
                # Content-Length may be absent or reflect remaining bytes
                content_length = resp.headers.get("Content-Length")
                total = (int(content_length) + existing_size) if content_length else 0

                mode = "ab" if existing_size > 0 else "wb"
                downloaded = existing_size
                start_time = time.monotonic()
                speed = 0.0

                with open(output_path, mode) as f:
                    while True:
                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.monotonic() - start_time
                        speed = (downloaded - existing_size) / elapsed if elapsed > 0 else 0
                        callback(downloaded, total, speed)

            print()  # newline after progress bar
            return os.path.abspath(output_path)

        except (urllib.error.URLError, OSError) as e:
            if attempt < MAX_RETRIES:
                print(f"\n  ⚠ Attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                # Update existing_size for resume
                if os.path.exists(output_path):
                    existing_size = os.path.getsize(output_path)
            else:
                raise RuntimeError(f"Download failed after {MAX_RETRIES} attempts: {e}") from e


def download_stream(
    stream,           # StreamInfo from extractor
    video_info,       # VideoInfo from extractor
    output_dir: str,
    callback: Optional[ProgressCallback] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Download a specific stream to output_dir.

    Args:
        stream: StreamInfo object with url, ext, quality, etc.
        video_info: VideoInfo for title and metadata.
        output_dir: Directory to save the file.
        callback: Custom progress callback.
        filename: Override output filename (without extension).

    Returns:
        Absolute path of downloaded file.
    """
    ensure_dir(output_dir)

    if filename:
        base_name = sanitize_filename(filename)
    else:
        quality_tag = f"[{stream.quality}]" if stream.quality != "unknown" else ""
        base_name = sanitize_filename(f"{video_info.title} {quality_tag}")

    output_path = os.path.join(output_dir, f"{base_name}.{stream.ext}")

    # Avoid overwriting — append counter
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(output_dir, f"{base_name} ({counter}).{stream.ext}")
        counter += 1

    print(f"  → Saving to: {os.path.basename(output_path)}")
    print(f"  → Quality:   {stream.quality} | {stream.stream_type} | {stream.codec}")
    if stream.filesize:
        print(f"  → Size:      ~{format_bytes(stream.filesize)}")

    return download_url(stream.url, output_path, callback)
