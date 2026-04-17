"""
YTDown Web Server — Phase 4: Playlist Support

Built-in HTTP server with:
  GET  /                       → index.html
  GET  /static/*               → CSS/JS assets
  POST /api/info               → fetch single video info JSON
  POST /api/playlist-info      → fetch playlist metadata + entry list
  POST /api/download           → start single download, return job_id
  POST /api/playlist-download  → start batch playlist download
  GET  /api/progress/<id>      → SSE stream with progress events
  GET  /api/jobs               → list active/completed jobs
  GET  /api/status             → server/ffmpeg status
  GET  /downloads/<file>       → serve downloaded file
"""

import io
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

# Force UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.downloader import download_url, download_with_audio
from core.extractor import StreamInfo, VideoInfo, get_best_stream, get_video_info
from core.merger import get_ffmpeg_version, is_ffmpeg_available
from core.playlist import PlaylistInfo, PlaylistEntry, get_playlist_info, is_playlist_url
from core.utils import ensure_dir, format_bytes, sanitize_filename

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR   = os.path.join(BASE_DIR, "static")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
ensure_dir(DOWNLOAD_DIR)

# ─── Job Store ────────────────────────────────────────────────────────────────

class DownloadJob:
    """Tracks the state of a single download job."""

    def __init__(self, job_id: str, video_id: str, title: str, quality: str, audio_only: bool,
                 playlist_id: str = "", playlist_index: int = 0, playlist_total: int = 0):
        self.job_id         = job_id
        self.video_id       = video_id
        self.title          = title
        self.quality        = quality
        self.audio_only     = audio_only
        self.playlist_id    = playlist_id      # non-empty = part of a batch
        self.playlist_index = playlist_index
        self.playlist_total = playlist_total

        self.status: str            = "pending"
        self.step: str              = ""
        self.downloaded: int        = 0
        self.total: int             = 0
        self.speed: float           = 0.0
        self.progress: float        = 0.0
        self.output_file: str       = ""
        self.error: str             = ""
        self.created_at: float      = time.time()
        self.completed_at: float    = 0.0

        self._events: list[str]     = []
        self._lock: threading.Lock  = threading.Lock()

    def push_event(self, data: dict) -> None:
        with self._lock:
            self._events.append(json.dumps(data))

    def pop_events(self, since: int) -> list[str]:
        with self._lock:
            return self._events[since:]

    def to_dict(self) -> dict:
        return {
            "job_id":           self.job_id,
            "video_id":         self.video_id,
            "title":            self.title,
            "quality":          self.quality,
            "audio_only":       self.audio_only,
            "playlist_id":      self.playlist_id,
            "playlist_index":   self.playlist_index,
            "playlist_total":   self.playlist_total,
            "status":           self.status,
            "step":             self.step,
            "downloaded":       self.downloaded,
            "total":            self.total,
            "speed":            round(self.speed),
            "progress":         round(self.progress, 1),
            "output_file":      os.path.basename(self.output_file) if self.output_file else "",
            "error":            self.error,
            "created_at":       self.created_at,
        }


_jobs: dict[str, DownloadJob] = {}
_jobs_lock = threading.Lock()


def _create_job(video_id: str, title: str, quality: str, audio_only: bool,
                playlist_id: str = "", playlist_index: int = 0,
                playlist_total: int = 0) -> DownloadJob:
    job_id = str(uuid.uuid4())
    job = DownloadJob(job_id, video_id, title, quality, audio_only,
                      playlist_id, playlist_index, playlist_total)
    with _jobs_lock:
        _jobs[job_id] = job
    return job


def _get_job(job_id: str) -> Optional[DownloadJob]:
    with _jobs_lock:
        return _jobs.get(job_id)


# ─── Download Worker ──────────────────────────────────────────────────────────

def _run_download(job: DownloadJob, info: VideoInfo, stream: StreamInfo,
                  audio_only: bool, audio_format: str) -> None:
    """Run a download job in a background thread."""

    def _make_callback(step_label: str):
        def cb(downloaded: int, total: int, speed: float) -> None:
            job.step       = step_label
            job.downloaded = downloaded
            job.total      = total
            job.speed      = speed
            if total > 0:
                job.progress = (downloaded / total) * 100
            job.push_event({
                "type":       "progress",
                "step":       step_label,
                "downloaded": downloaded,
                "total":      total,
                "speed":      round(speed),
                "progress":   round(job.progress, 1),
            })
        return cb

    try:
        job.status = "running"
        job.push_event({"type": "start", "title": job.title, "quality": job.quality})

        # Patch download_url to use our labelled callbacks
        import core.downloader as dl_module

        original_download_url = dl_module.download_url

        def patched_download_url(url, output_path, callback=None, resume=True):
            label = job.step or "Downloading"
            return original_download_url(url, output_path, _make_callback(label), resume)

        dl_module.download_url = patched_download_url

        try:
            output_path = download_with_audio(
                video_stream=stream,
                video_info=info,
                output_dir=DOWNLOAD_DIR,
                audio_only=audio_only,
                audio_format=audio_format,
            )
        finally:
            dl_module.download_url = original_download_url

        job.status       = "done"
        job.progress     = 100.0
        job.output_file  = output_path
        job.completed_at = time.time()
        job.push_event({
            "type":        "done",
            "output_file": os.path.basename(output_path),
            "progress":    100,
        })

    except Exception as e:
        job.status = "error"
        job.error  = str(e)
        job.push_event({"type": "error", "message": str(e)})


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def _send_json(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    _send_json(handler, {"error": message}, status)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


# ─── Request Handler ──────────────────────────────────────────────────────────

class YTDownHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Quiet logger — only log errors
        if args and str(args[1]) not in ("200", "206"):
            print(f"  [{self.address_string()}] {fmt % args}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        if path in ("/", "/index.html"):
            self._serve_file(os.path.join(STATIC_DIR, "index.html"))
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
            self._serve_file(os.path.join(STATIC_DIR, rel))
        elif path.startswith("/api/progress/"):
            job_id = path[len("/api/progress/"):]
            self._handle_progress_sse(job_id)
        elif path == "/api/jobs":
            self._handle_jobs()
        elif path == "/api/status":
            self._handle_status()
        elif path.startswith("/downloads/"):
            filename = urllib.parse.unquote(path[len("/downloads/"):])
            self._serve_file(os.path.join(DOWNLOAD_DIR, filename), download=True)
        else:
            _send_error(self, "Not found", 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/info":
            self._handle_info()
        elif path == "/api/download":
            self._handle_download()
        elif path == "/api/playlist-info":
            self._handle_playlist_info()
        elif path == "/api/playlist-download":
            self._handle_playlist_download()
        else:
            _send_error(self, "Not found", 404)

    # ── Route Handlers ─────────────────────────────────────────────────────

    def _handle_status(self):
        ffmpeg_version = get_ffmpeg_version()
        _send_json(self, {
            "ffmpeg": {
                "available": is_ffmpeg_available(),
                "version": ffmpeg_version or "",
            },
            "downloads_dir": DOWNLOAD_DIR,
        })

    def _handle_info(self):
        try:
            body = _read_json_body(self)
            url  = body.get("url", "").strip()
            if not url:
                return _send_error(self, "Missing 'url' field")

            info = get_video_info(url)

            streams = []
            for s in info.streams:
                streams.append({
                    "itag":        s.itag,
                    "quality":     s.quality,
                    "stream_type": s.stream_type,
                    "codec":       s.codec,
                    "ext":         s.ext,
                    "mime_type":   s.mime_type,
                    "bitrate":     s.bitrate,
                    "filesize":    s.filesize,
                    "width":       s.width,
                    "height":      s.height,
                    "fps":         s.fps,
                    "label":       s.label(),
                })

            _send_json(self, {
                "video_id":        info.video_id,
                "title":           info.title,
                "channel":         info.channel,
                "duration":        info.duration_seconds,
                "duration_str":    info.duration_str,
                "thumbnail":       info.thumbnail,
                "url":             info.url,
                "streams":         streams,
                "stream_counts": {
                    "video":  len(info.video_streams()),
                    "audio":  len(info.audio_streams()),
                    "muxed":  len(info.muxed_streams()),
                    "total":  len(info.streams),
                },
            })
        except Exception as e:
            _send_error(self, str(e))

    def _handle_download(self):
        try:
            body        = _read_json_body(self)
            url         = body.get("url", "").strip()
            quality     = body.get("quality", "best")
            audio_only  = body.get("audio_only", False)
            audio_format= body.get("audio_format", "m4a")

            if not url:
                return _send_error(self, "Missing 'url' field")

            # Fetch info synchronously (fast)
            info = get_video_info(url)

            if audio_only:
                audio_streams = info.audio_streams()
                if not audio_streams:
                    return _send_error(self, "No audio streams available")
                stream = audio_streams[0]
            else:
                stream = get_best_stream(info, quality=quality, prefer_mp4=True)

            job = _create_job(
                video_id   = info.video_id,
                title      = info.title,
                quality    = "audio" if audio_only else stream.quality,
                audio_only = audio_only,
            )

            # Start background download thread
            t = threading.Thread(
                target=_run_download,
                args=(job, info, stream, audio_only, audio_format),
                daemon=True,
            )
            t.start()

            _send_json(self, {"job_id": job.job_id, "title": info.title, "quality": job.quality})

        except Exception as e:
            _send_error(self, str(e))

    def _handle_progress_sse(self, job_id: str):
        """Server-Sent Events stream for live progress."""
        job = _get_job(job_id)
        if not job:
            return _send_error(self, "Job not found", 404)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        cursor = 0
        try:
            while True:
                events = job.pop_events(cursor)
                for ev in events:
                    self.wfile.write(f"data: {ev}\n\n".encode("utf-8"))
                    self.wfile.flush()
                cursor += len(events)

                if job.status in ("done", "error"):
                    # Send final state then close
                    time.sleep(0.1)
                    remaining = job.pop_events(cursor)
                    for ev in remaining:
                        self.wfile.write(f"data: {ev}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    break

                time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_jobs(self):
        with _jobs_lock:
            jobs = [j.to_dict() for j in _jobs.values()]
        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        _send_json(self, {"jobs": jobs[:50]})

    def _handle_playlist_info(self):
        """Return playlist metadata + first 200 entries."""
        try:
            body = _read_json_body(self)
            url  = body.get("url", "").strip()
            if not url:
                return _send_error(self, "Missing 'url' field")
            if not is_playlist_url(url):
                return _send_error(self, "URL does not contain a playlist ID (list= param)")

            playlist = get_playlist_info(url)
            entries  = [
                {
                    "video_id":  e.video_id,
                    "title":     e.title,
                    "duration":  e.duration,
                    "thumbnail": e.thumbnail,
                    "channel":   e.channel,
                    "index":     e.index,
                }
                for e in playlist.entries
            ]
            _send_json(self, {
                "playlist_id": playlist.playlist_id,
                "title":       playlist.title,
                "channel":     playlist.channel,
                "video_count": playlist.video_count,
                "thumbnail":   playlist.thumbnail,
                "url":         playlist.url,
                "entries":     entries,
            })
        except Exception as e:
            _send_error(self, str(e))

    def _handle_playlist_download(self):
        """Start a batch download for selected playlist entries."""
        try:
            body         = _read_json_body(self)
            video_ids    = body.get("video_ids", [])   # list of video IDs to download
            playlist_id  = body.get("playlist_id", "")
            quality      = body.get("quality", "best")
            audio_only   = body.get("audio_only", False)
            audio_format = body.get("audio_format", "m4a")

            if not video_ids:
                return _send_error(self, "No video_ids provided")

            total    = len(video_ids)
            job_ids  = []

            # Create a placeholder job per video
            for idx, vid in enumerate(video_ids, 1):
                job = _create_job(
                    video_id      = vid,
                    title         = f"Video {idx}/{total}",  # Updated when fetched
                    quality       = quality,
                    audio_only    = audio_only,
                    playlist_id   = playlist_id,
                    playlist_index= idx,
                    playlist_total= total,
                )
                job_ids.append(job.job_id)

            # One background thread runs all downloads sequentially
            def _batch_worker():
                for job_id, vid in zip(job_ids, video_ids):
                    job = _get_job(job_id)
                    if not job:
                        continue
                    try:
                        info = get_video_info(vid)
                        job.title    = info.title
                        job.video_id = info.video_id

                        if audio_only:
                            stream = info.audio_streams()[0] if info.audio_streams() else None
                            if not stream:
                                raise RuntimeError("No audio stream")
                        else:
                            stream = get_best_stream(info, quality=quality, prefer_mp4=True)
                            job.quality = stream.quality

                        _run_download(job, info, stream, audio_only, audio_format)
                    except Exception as e:
                        job.status = "error"
                        job.error  = str(e)
                        job.push_event({"type": "error", "message": str(e)})

            t = threading.Thread(target=_batch_worker, daemon=True)
            t.start()

            _send_json(self, {"job_ids": job_ids, "total": total})

        except Exception as e:
            _send_error(self, str(e))

    def _serve_file(self, path: str, download: bool = False):
        if not os.path.isfile(path):
            return _send_error(self, f"File not found: {os.path.basename(path)}", 404)

        mime, _ = mimetypes.guess_type(path)
        mime = mime or "application/octet-stream"
        size = os.path.getsize(path)

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        if download:
            fname = urllib.parse.quote(os.path.basename(path))
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.end_headers()

        with open(path, "rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)


# ─── Entry Point ──────────────────────────────────────────────────────────────

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the YTDown web server."""
    server = ThreadingHTTPServer((host, port), YTDownHandler)

    ffmpeg_ver = get_ffmpeg_version()
    ffmpeg_status = f"v{ffmpeg_ver}" if ffmpeg_ver else "not found"

    print(f"""
  +=========================================+
  |   YTDown Web Server — Phase 4          |
  |   Playlist Support                     |
  +=========================================+

  Listening : http://{host}:{port}
  Downloads : {DOWNLOAD_DIR}
  FFmpeg    : {ffmpeg_status}

  Press Ctrl+C to stop.
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  [!] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="YTDown Web Server")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args()
    run_server(args.host, args.port)
