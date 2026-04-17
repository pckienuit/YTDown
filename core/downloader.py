"""Chunked downloader with progress reporting and smart quality selection."""

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from core.utils import HEADERS, ensure_dir, format_bytes, format_speed, sanitize_filename

# ─── Config ───────────────────────────────────────────────────────────────────

CHUNK_SIZE      = 1024 * 1024      # 1 MB per read — much faster than 8 KB
PART_SIZE       = 8 * 1024 * 1024  # 8 MB per parallel part
MAX_WORKERS     = 4                # parallel connections
MAX_RETRIES     = 3
RETRY_DELAY     = 1.5              # seconds
MIN_PARALLEL    = 5 * 1024 * 1024  # only use parallel if file > 5 MB

ProgressCallback = Callable[[int, int, float], None]
# Args: (downloaded_bytes, total_bytes, speed_bps)


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
    dl_str  = format_bytes(downloaded)
    tot_str = format_bytes(total) if total > 0 else "?"
    return f"[{bar}] {pct:5.1f}% | {dl_str} / {tot_str}"


def _console_progress(downloaded: int, total: int, speed: float) -> None:
    """Default console progress callback."""
    bar = _make_progress_bar(downloaded, total)
    speed_str = format_speed(speed)
    if total > 0 and speed > 0:
        eta_s = (total - downloaded) / speed
        h, r  = divmod(int(eta_s), 3600)
        m, s  = divmod(r, 60)
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
            h, r  = divmod(int(eta_s), 3600)
            m, s  = divmod(r, 60)
            eta_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            print(f"\r  [{label}] {bar} | {speed_str} | ETA {eta_str} ", end="", flush=True)
        else:
            print(f"\r  [{label}] {bar} | {speed_str}        ", end="", flush=True)
    return cb


# ─── HTTP Probe ───────────────────────────────────────────────────────────────

def _probe(url: str) -> tuple[int, bool]:
    """
    HEAD request to get Content-Length and check Accept-Ranges support.
    Returns (content_length, supports_ranges).
    """
    try:
        req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            cl = resp.headers.get("Content-Length")
            ar = resp.headers.get("Accept-Ranges", "none").lower()
            return (int(cl) if cl else 0), (ar == "bytes")
    except Exception:
        return 0, False


# ─── Single-connection download (fallback / small files) ─────────────────────

def _download_single(
    url: str,
    output_path: str,
    callback: ProgressCallback,
    existing_size: int = 0,
) -> None:
    """Simple streaming download, single TCP connection."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = dict(HEADERS)
            if existing_size > 0:
                headers["Range"] = f"bytes={existing_size}-"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                # HTTP 206 Partial Content
                cl    = resp.headers.get("Content-Length")
                total = (int(cl) + existing_size) if cl else 0

                # If server returns 200 despite Range header (no range support),
                # start fresh to avoid appending duplicate data
                if resp.status == 200 and existing_size > 0:
                    existing_size = 0

                mode       = "ab" if existing_size > 0 else "wb"
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
                        speed   = (downloaded - existing_size) / elapsed if elapsed > 0 else 0
                        callback(downloaded, total, speed)
            return

        except urllib.error.HTTPError as e:
            if e.code == 416:
                # Range not satisfiable = file already complete, nothing to do
                return
            if attempt < MAX_RETRIES:
                print(f"\n  [!] Attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                if os.path.exists(output_path):
                    existing_size = os.path.getsize(output_path)
            else:
                raise RuntimeError(f"Download failed after {MAX_RETRIES} attempts: {e}") from e

        except (urllib.error.URLError, OSError) as e:
            if attempt < MAX_RETRIES:
                print(f"\n  [!] Attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                if os.path.exists(output_path):
                    existing_size = os.path.getsize(output_path)
            else:
                raise RuntimeError(f"Download failed after {MAX_RETRIES} attempts: {e}") from e



# ─── Parallel Multi-Part Download ─────────────────────────────────────────────

def _download_part(
    url: str,
    start: int,
    end: int,
    part_path: str,
    errors: list,
    idx: int,
) -> None:
    """Download a byte range into a temp file. Runs in a thread."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = dict(HEADERS)
            headers["Range"] = f"bytes={start}-{end}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(part_path, "wb") as f:
                    while True:
                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
            return
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                errors.append(f"Part {idx} failed: {e}")


def _download_parallel(
    url: str,
    output_path: str,
    total_size: int,
    callback: ProgressCallback,
    workers: int = MAX_WORKERS,
) -> None:
    """
    Split the download into parts and fetch them in parallel threads.
    Reassemble after all parts complete.
    """
    # Build byte ranges
    parts: list[tuple[int, int]] = []
    pos = 0
    while pos < total_size:
        end = min(pos + PART_SIZE - 1, total_size - 1)
        parts.append((pos, end))
        pos = end + 1

    n_parts   = len(parts)
    base_dir  = os.path.dirname(output_path) or "."
    part_paths = [f"{output_path}.part{i}" for i in range(n_parts)]
    errors: list[str] = []

    # Atomic shared counter for progress
    downloaded_total = [0]
    lock = threading.Lock()
    start_time = time.monotonic()

    def progress_thread():
        while True:
            with lock:
                dl = downloaded_total[0]
            elapsed = time.monotonic() - start_time
            speed = dl / elapsed if elapsed > 0 else 0
            callback(dl, total_size, speed)
            if dl >= total_size:
                break
            time.sleep(0.25)

    # Wrap _download_part to update progress atomically
    def download_part_tracked(url, start, end, path, errors, idx):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                headers = dict(HEADERS)
                headers["Range"] = f"bytes={start}-{end}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    with open(path, "wb") as f:
                        while True:
                            chunk = resp.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                            with lock:
                                downloaded_total[0] += len(chunk)
                return
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    errors.append(f"Part {idx} failed: {e}")

    # Start progress reporter
    prog = threading.Thread(target=progress_thread, daemon=True)
    prog.start()

    # Dispatch parts in batches of `workers`
    all_threads: list[threading.Thread] = []
    for i, (start, end) in enumerate(parts):
        t = threading.Thread(
            target=download_part_tracked,
            args=(url, start, end, part_paths[i], errors, i),
            daemon=True,
        )
        all_threads.append(t)

    # Run up to `workers` at a time
    active: list[threading.Thread] = []
    for t in all_threads:
        while len([x for x in active if x.is_alive()]) >= workers:
            time.sleep(0.05)
        t.start()
        active.append(t)

    for t in active:
        t.join()

    # Ensure progress hits 100%
    with lock:
        downloaded_total[0] = total_size
    time.sleep(0.3)  # let progress thread print final update

    if errors:
        for p in part_paths:
            try: os.remove(p)
            except OSError: pass
        raise RuntimeError("Parallel download failed:\n" + "\n".join(errors))

    # Reassemble parts → output file
    with open(output_path, "wb") as out:
        for path in part_paths:
            with open(path, "rb") as pf:
                while True:
                    buf = pf.read(CHUNK_SIZE)
                    if not buf:
                        break
                    out.write(buf)
            try:
                os.remove(path)
            except OSError:
                pass


# ─── Public download_url ──────────────────────────────────────────────────────

def download_url(
    url: str,
    output_path: str,
    callback: Optional[ProgressCallback] = None,
    resume: bool = True,
) -> str:
    """
    Download a URL to output_path with progress.

    Automatically uses parallel multi-part download for files > 5 MB
    when the server supports Accept-Ranges (almost all YouTube CDN servers do).

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

    # Probe the server for size and range support
    total_size, supports_ranges = _probe(url)

    # Skip if already complete
    if total_size > 0 and existing_size >= total_size:
        callback(total_size, total_size, 0)
        print()
        return os.path.abspath(output_path)

    use_parallel = (
        supports_ranges
        and total_size >= MIN_PARALLEL
        and existing_size == 0
    )

    if use_parallel:
        _download_parallel(url, output_path, total_size, callback, workers=MAX_WORKERS)
    else:
        _download_single(url, output_path, callback, existing_size)

    print()
    return os.path.abspath(output_path)



# ─── download_stream ──────────────────────────────────────────────────────────

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
        base_name   = sanitize_filename(f"{video_info.title} {quality_tag}")

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


# ─── Smart Download (auto video+audio merge) ─────────────────────────────────

def _pick_best_audio(video_info, prefer_mp4: bool = True):
    """Select the best audio stream from video_info."""
    audio_streams = video_info.audio_streams()
    if not audio_streams:
        return None
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
            tmp_audio   = os.path.join(output_dir, f"{base_name}_audio_tmp.{audio_stream.ext}")
            download_url(audio_stream.url, tmp_audio, _labeled_progress("Audio"))
            output_path = os.path.join(output_dir, f"{base_name}.mp3")
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"{base_name} ({counter}).mp3")
                counter += 1
            return extract_audio_as_mp3(tmp_audio, output_path, remove_source=True)

        else:
            # m4a / no FFmpeg → download native audio directly
            output_path = os.path.join(output_dir, f"{base_name}.{audio_stream.ext}")
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"{base_name} ({counter}).{audio_stream.ext}")
                counter += 1
            return download_url(audio_stream.url, output_path, _labeled_progress("Audio"))

    # ── Video download ──────────────────────────────────────────────────────
    if video_stream.stream_type == "muxed":
        return download_stream(video_stream, video_info, output_dir)

    if video_stream.stream_type == "video":
        audio_stream = _pick_best_audio(video_info, prefer_mp4=(video_stream.ext == "mp4"))

        if audio_stream and is_ffmpeg_available():
            quality_tag = video_stream.quality
            tmp_video   = os.path.join(output_dir, f"{base_name}_video_tmp.{video_stream.ext}")
            tmp_audio   = os.path.join(output_dir, f"{base_name}_audio_tmp.{audio_stream.ext}")

            v_size = video_stream.filesize or 0
            a_size = audio_stream.filesize or 0
            total_size = v_size + a_size
            if total_size:
                print(f"  -> Total size: ~{format_bytes(total_size)} (video + audio, downloading simultaneously)")

            # ── Download video + audio simultaneously ───────────────────────
            # Shared state for combined progress display
            v_bytes = [0]
            a_bytes = [0]
            lock    = threading.Lock()
            start_t = time.monotonic()
            done    = [False]

            def combined_progress():
                """Print aggregate speed every 200 ms."""
                while not done[0]:
                    with lock:
                        dl = v_bytes[0] + a_bytes[0]
                    elapsed = time.monotonic() - start_t
                    speed   = dl / elapsed if elapsed > 0 else 0

                    bar = _make_progress_bar(dl, total_size, width=28)
                    spd = format_speed(speed)
                    if total_size > 0 and speed > 0:
                        eta_s = (total_size - dl) / speed
                        m, s  = divmod(int(eta_s), 60)
                        eta   = f"{m}:{s:02d}"
                        print(f"\r  [DL] {bar} | {spd} | ETA {eta} ", end="", flush=True)
                    else:
                        print(f"\r  [DL] {bar} | {spd}        ", end="", flush=True)
                    time.sleep(0.2)

            def track_video(dl, total, speed):
                with lock:
                    v_bytes[0] = dl

            def track_audio(dl, total, speed):
                with lock:
                    a_bytes[0] = dl

            prog_thread = threading.Thread(target=combined_progress, daemon=True)
            prog_thread.start()

            v_err: list[str] = []
            a_err: list[str] = []

            def dl_video():
                try:
                    download_url(video_stream.url, tmp_video, track_video)
                except Exception as e:
                    v_err.append(str(e))

            def dl_audio():
                try:
                    download_url(audio_stream.url, tmp_audio, track_audio)
                except Exception as e:
                    a_err.append(str(e))

            t_v = threading.Thread(target=dl_video)
            t_a = threading.Thread(target=dl_audio)
            t_v.start()
            t_a.start()
            t_v.join()
            t_a.join()

            done[0] = True
            prog_thread.join(timeout=0.5)
            print()  # newline after progress

            if v_err or a_err:
                raise RuntimeError(
                    "Download failed:\n"
                    + ("\n".join(v_err) if v_err else "")
                    + ("\n".join(a_err) if a_err else "")
                )


            output_path = os.path.join(output_dir, f"{base_name} [{quality_tag}].mp4")
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"{base_name} [{quality_tag}] ({counter}).mp4")
                counter += 1

            print()
            return merge_video_audio(tmp_video, tmp_audio, output_path, remove_sources=True)

        elif audio_stream and not is_ffmpeg_available():
            muxed_streams = video_info.muxed_streams()
            if muxed_streams:
                best_muxed = muxed_streams[0]
                print(
                    f"\n  [!] FFmpeg not found — using muxed stream ({best_muxed.quality}).\n"
                    f"      Install FFmpeg for {video_stream.quality}: winget install ffmpeg\n"
                )
                return download_stream(best_muxed, video_info, output_dir)
            else:
                print(
                    "\n  [!] FFmpeg not found — saving video and audio as separate files.\n"
                    "      Merge tip: winget install ffmpeg  (then re-download for auto-merge)\n"
                )
                video_path = download_stream(video_stream, video_info, output_dir)
                audio_out  = os.path.join(output_dir, f"{base_name}.audio.{audio_stream.ext}")
                counter = 1
                while os.path.exists(audio_out):
                    audio_out = os.path.join(output_dir, f"{base_name}.audio ({counter}).{audio_stream.ext}")
                    counter += 1
                download_url(audio_stream.url, audio_out, _labeled_progress("Audio"))
                print(f"\n  -> Audio saved: {os.path.basename(audio_out)}")
                return video_path

        else:
            return download_stream(video_stream, video_info, output_dir)

    # Fallback: audio stream selected as main
    return download_stream(video_stream, video_info, output_dir)
