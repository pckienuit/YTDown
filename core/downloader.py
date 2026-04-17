"""Chunked downloader with progress reporting and smart quality selection."""

import os
import tempfile
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

    bar = "=" * filled + "-" * (width - filled)
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


def _labeled_progress(label: str) -> ProgressCallback:
    """Create a progress callback with a string label prefix."""
    def cb(downloaded: int, total: int, speed: float) -> None:
        bar = _make_progress_bar(downloaded, total, width=24)
        speed_str = format_speed(speed)
        if total > 0 and speed > 0:
            eta_s = (total - downloaded) / speed
            h, r = divmod(int(eta_s), 3600)
            m, s = divmod(r, 60)
            eta_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            print(f"\r  [{label}] {bar} | {speed_str} | ETA {eta_str} ", end="", flush=True)
        else:
            print(f"\r  [{label}] {bar} | {speed_str}        ", end="", flush=True)
    return cb


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
                content_length = resp.headers.get("Content-Length")
                total = (int(content_length) + existing_size) if content_length else 0

                mode = "ab" if existing_size > 0 else "wb"
                downloaded = existing_size
                start_time = time.monotonic()

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
                print(f"\n  [!] Attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                if os.path.exists(output_path):
                    existing_size = os.path.getsize(output_path)
            else:
                raise RuntimeError(f"Download failed after {MAX_RETRIES} attempts: {e}") from e


def download_stream(
    stream,
    video_info,
    output_dir: str,
    callback: Optional[ProgressCallback] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Download a single stream to output_dir.

    Args:
        stream: StreamInfo with url, ext, quality, stream_type, codec.
        video_info: VideoInfo for title metadata.
        output_dir: Directory to save file.
        callback: Custom progress callback.
        filename: Override base filename (without extension).

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

    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(output_dir, f"{base_name} ({counter}).{stream.ext}")
        counter += 1

    print(f"  -> Saving to: {os.path.basename(output_path)}")
    print(f"  -> Quality:   {stream.quality} | {stream.stream_type} | {stream.codec}")
    if stream.filesize:
        print(f"  -> Size:      ~{format_bytes(stream.filesize)}")

    return download_url(stream.url, output_path, callback)


# ─── Smart Download (Phase 2) ─────────────────────────────────────────────────

def _pick_best_audio(video_info, prefer_mp4: bool = True):
    """Select the best audio stream from video_info."""
    audio_streams = video_info.audio_streams()
    if not audio_streams:
        return None
    # Prefer m4a (mp4 container) for compatibility
    if prefer_mp4:
        mp4_audio = [s for s in audio_streams if s.ext == "mp4"]
        if mp4_audio:
            return mp4_audio[0]
    return audio_streams[0]


def download_with_audio(
    video_stream,
    video_info,
    output_dir: str,
    audio_only: bool = False,
    audio_format: str = "mp3",
) -> str:
    """
    Smart download that handles all cases:
      - muxed stream   → direct download (audio already included)
      - video stream   → download video + best audio → FFmpeg merge
      - audio_only     → download best audio → optionally convert to MP3

    Args:
        video_stream: Selected StreamInfo (video, audio, or muxed).
        video_info: Full VideoInfo with all streams.
        output_dir: Output directory.
        audio_only: If True, download audio only.
        audio_format: "mp3" | "m4a" | "copy" (for audio_only mode).

    Returns:
        Absolute path of final output file.
    """
    from core.merger import (
        extract_audio_as_mp3,
        extract_audio_copy,
        find_ffmpeg,
        is_ffmpeg_available,
        merge_video_audio,
    )

    ensure_dir(output_dir)
    base_name = sanitize_filename(video_info.title)

    # ── Audio-only download ─────────────────────────────────────────────────
    if audio_only:
        audio_stream = _pick_best_audio(video_info)
        if not audio_stream:
            raise RuntimeError("No audio streams available for this video.")

        print(f"  -> Audio stream: {audio_stream.quality} [{audio_stream.codec}]")

        if audio_format == "mp3" and is_ffmpeg_available():
            # Download to temp, convert to MP3
            tmp_audio = os.path.join(output_dir, f"{base_name}_audio_tmp.{audio_stream.ext}")
            download_url(audio_stream.url, tmp_audio, _labeled_progress("Audio"))
            output_path = os.path.join(output_dir, f"{base_name}.mp3")
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"{base_name} ({counter}).mp3")
                counter += 1
            return extract_audio_as_mp3(tmp_audio, output_path, remove_source=True)

        elif audio_format == "m4a" or not is_ffmpeg_available():
            # Download native audio (m4a/webm) directly
            output_path = os.path.join(output_dir, f"{base_name}.{audio_stream.ext}")
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"{base_name} ({counter}).{audio_stream.ext}")
                counter += 1
            return download_url(audio_stream.url, output_path, _labeled_progress("Audio"))

        else:
            # copy mode — download and extract audio track via ffmpeg
            tmp_audio = os.path.join(output_dir, f"{base_name}_audio_tmp.{audio_stream.ext}")
            download_url(audio_stream.url, tmp_audio, _labeled_progress("Audio"))
            output_path = os.path.join(output_dir, f"{base_name}_audio.{audio_stream.ext}")
            return extract_audio_copy(tmp_audio, output_path, remove_source=True)

    # ── Video download ──────────────────────────────────────────────────────
    if video_stream.stream_type == "muxed":
        # Muxed: audio already included, direct download
        return download_stream(video_stream, video_info, output_dir)

    if video_stream.stream_type == "video":
        # Adaptive video: need to merge with audio
        audio_stream = _pick_best_audio(video_info, prefer_mp4=(video_stream.ext == "mp4"))

        if audio_stream and is_ffmpeg_available():
            # Download both streams then merge
            quality_tag = video_stream.quality
            tmp_video = os.path.join(output_dir, f"{base_name}_video_tmp.{video_stream.ext}")
            tmp_audio = os.path.join(output_dir, f"{base_name}_audio_tmp.{audio_stream.ext}")

            total_size = (video_stream.filesize or 0) + (audio_stream.filesize or 0)
            if total_size:
                print(f"  -> Total size: ~{format_bytes(total_size)} (video + audio)")

            print(f"\n  [1/2] Downloading video ({video_stream.quality})...")
            download_url(video_stream.url, tmp_video, _labeled_progress("Video"))

            print(f"  [2/2] Downloading audio ({audio_stream.quality})...")
            download_url(audio_stream.url, tmp_audio, _labeled_progress("Audio"))

            output_path = os.path.join(output_dir, f"{base_name} [{quality_tag}].mp4")
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"{base_name} [{quality_tag}] ({counter}).mp4")
                counter += 1

            print()
            return merge_video_audio(tmp_video, tmp_audio, output_path, remove_sources=True)

        elif audio_stream and not is_ffmpeg_available():
            # No FFmpeg — download video only with a warning
            print(
                "\n  [!] FFmpeg not found — downloading video-only (no audio).\n"
                "      Install FFmpeg for automatic audio merging.\n"
                "      https://ffmpeg.org/download.html\n"
            )
            return download_stream(video_stream, video_info, output_dir)

        else:
            # No audio stream available at all
            return download_stream(video_stream, video_info, output_dir)

    # Fallback: audio stream selected as main (shouldn't happen in normal flow)
    return download_stream(video_stream, video_info, output_dir)
