"""
YouTube video information extractor.

Uses InnerTube API to get direct streaming URLs.
"""

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from core.utils import format_duration, quality_sort_key, get_browser_headers


_INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player"
_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"


@dataclass
class StreamInfo:
    itag: int
    url: str
    mime_type: str
    quality: str
    stream_type: str
    codec: str
    bitrate: int
    filesize: Optional[int]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[int]
    ext: str

    def label(self) -> str:
        if self.stream_type == "audio":
            return f"Audio {self.quality} [{self.ext}]"
        fps_str = f" {self.fps}fps" if self.fps and self.fps > 30 else ""
        return f"{self.quality}{fps_str} [{self.stream_type}] [{self.ext}]"


@dataclass
class VideoInfo:
    video_id: str
    title: str
    duration_seconds: int
    channel: str
    thumbnail: str
    streams: list[StreamInfo] = field(default_factory=list)

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration_seconds)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def muxed_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.stream_type == "muxed"]

    def video_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.stream_type == "video"]

    def audio_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.stream_type == "audio"]


# ─── Visitor Data ────────────────────────────────────────────────────────────

_visitor_data_cache: str = ""


def _get_visitor_data(session: requests.Session) -> str:
    """Extract visitorData from cookies (env var or session)."""
    global _visitor_data_cache
    if _visitor_data_cache:
        return _visitor_data_cache

    # 1. Environment variable override
    env_visitor = os.environ.get("VISITOR_DATA")
    if env_visitor:
        _visitor_data_cache = env_visitor
        print("  [DEBUG] Using VISITOR_DATA from environment")
        return _visitor_data_cache

    # 2. Extract from session cookies (preferred for serverless)
    visitor = session.cookies.get("VISITOR_INFO1_DATA")
    if not visitor:
        visitor = session.cookies.get("VISITOR_DATA")

    if visitor:
        _visitor_data_cache = visitor
        print(f"  [DEBUG] Using VISITOR_DATA from cookies: {visitor[:20]}...")
        return _visitor_data_cache

    # 3. Fallback: fetch from YouTube homepage
    try:
        headers = get_browser_headers()
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

        resp = session.get("https://www.youtube.com/", headers=headers, timeout=10)
        html = resp.text

        patterns = [
            r'"VISITOR_DATA"\s*:\s*"([^"]+)"',
            r'"visitorData"\s*:\s*"([^"]+)"',
        ]

        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                _visitor_data_cache = m.group(1)
                print(f"  [DEBUG] Got visitorData from homepage: {_visitor_data_cache[:20]}...")
                return _visitor_data_cache

        print("  [WARN] Could not find VISITOR_DATA")
    except Exception as e:
        print(f"  [WARN] Failed to fetch VISITOR_DATA: {e}")

    return ""


# ─── Session Management ──────────────────────────────────────────────────────

def _create_session() -> requests.Session:
    """Create a requests session with cookies."""
    session = requests.Session()

    cookies_raw = os.environ.get("YOUTUBE_COOKIES")
    if not cookies_raw:
        return session

    # Try JSON format first (DevTools export)
    try:
        import json
        data = json.loads(cookies_raw)
        cookies_list = data.get("cookies", [])
        if cookies_list:
            for c in cookies_list:
                name = c.get("name", "")
                value = c.get("value", "")
                domain = c.get("domain", ".youtube.com")
                if name and value:
                    session.cookies.set(name, value, domain=domain)
            print(f"  [DEBUG] Loaded {len(cookies_list)} cookies from JSON format")
            return session
    except (json.JSONDecodeError, ImportError):
        pass

    # String format: name=value; name2=value2
    for part in cookies_raw.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            name = name.strip()
            value = value.strip()
            session.cookies.set(name, value, domain=".youtube.com")

    return session


# ─── InnerTube API ───────────────────────────────────────────────────────────

_CLIENT_ORDER = ["ANDROID", "IOS", "ANDROID_VR", "TVHTML5", "WEB"]


def _generate_sapisidhash(session: requests.Session) -> Optional[str]:
    """Generate SAPISIDHASH from SAPISID cookie."""
    import time
    import hashlib

    sapisid = session.cookies.get("SAPISID")
    if not sapisid:
        sapisid = session.cookies.get("__Secure-3PAPISID")

    if not sapisid:
        return None

    timestamp = int(time.time())
    origin = "https://www.youtube.com"
    msg = f"{timestamp} {sapisid} {origin}"
    hash_str = hashlib.sha1(msg.encode("utf-8")).hexdigest()
    return f"SAPISIDHASH {timestamp}_{hash_str}"


def _innertube_request(video_id: str, client_name: str, session: requests.Session) -> dict:
    """Call InnerTube API."""
    client_configs = {
        "ANDROID": {
            "clientName": "ANDROID",
            "clientVersion": "19.30.36",
            "androidSdkVersion": 34,
        },
        "IOS": {
            "clientName": "IOS",
            "clientVersion": "19.29.1",
            "deviceMake": "Apple",
            "deviceModel": "iPhone16,2",
        },
        "ANDROID_VR": {
            "clientName": "ANDROID_VR",
            "clientVersion": "1.50.34",
        },
        "TVHTML5": {
            "clientName": "TVHTML5",
            "clientVersion": "1.20230619.04.00",
        },
        "WEB": {
            "clientName": "WEB",
            "clientVersion": "2.20240726.00.00",
        },
    }

    client = client_configs.get(client_name, client_configs["ANDROID"])
    context = {"client": dict(client)}

    visitor_data = _get_visitor_data(session)
    if visitor_data:
        context["client"]["visitorData"] = visitor_data

    payload = {
        "videoId": video_id,
        "context": context,
    }

    url = f"{_INNERTUBE_URL}?key={_INNERTUBE_KEY}&prettyPrint=false"

    headers = get_browser_headers()
    if visitor_data:
        headers["X-Goog-Visitor-Id"] = visitor_data

    # Add Authorization header for WEB client (required by YouTube)
    if client_name == "WEB":
        auth = _generate_sapisidhash(session)
        if auth:
            headers["Authorization"] = auth

    resp = session.post(url, json=payload, headers=headers, timeout=15)
    
    if resp.status_code == 429:
        raise RuntimeError("HTTP 429 Too Many Requests")
    if resp.status_code != 200:
        raise RuntimeError(f"InnerTube error: HTTP {resp.status_code}")

    return resp.json()


# ─── Stream Parsing ─────────────────────────────────────────────────────────

ITAG_MAP = {
    18:  {"quality": "360p",  "type": "muxed",  "ext": "mp4"},
    22:  {"quality": "720p",  "type": "muxed",  "ext": "mp4"},
    37:  {"quality": "1080p", "type": "muxed",  "ext": "mp4"},
    43:  {"quality": "360p",  "type": "muxed",  "ext": "webm"},
    44:  {"quality": "480p",  "type": "muxed",  "ext": "webm"},
    45:  {"quality": "720p",  "type": "muxed",  "ext": "webm"},
    137: {"quality": "1080p", "type": "video",  "ext": "mp4"},
    248: {"quality": "1080p", "type": "video",  "ext": "webm"},
    136: {"quality": "720p",  "type": "video",  "ext": "mp4"},
    247: {"quality": "720p",  "type": "video",  "ext": "webm"},
    135: {"quality": "480p",  "type": "video",  "ext": "mp4"},
    244: {"quality": "480p",  "type": "video",  "ext": "webm"},
    134: {"quality": "360p",  "type": "video",  "ext": "mp4"},
    243: {"quality": "360p",  "type": "video",  "ext": "webm"},
    133: {"quality": "240p",  "type": "video",  "ext": "mp4"},
    242: {"quality": "240p",  "type": "video",  "ext": "webm"},
    160: {"quality": "144p",  "type": "video",  "ext": "mp4"},
    278: {"quality": "144p",  "type": "video",  "ext": "webm"},
    271: {"quality": "1440p", "type": "video",  "ext": "webm"},
    264: {"quality": "1440p", "type": "video",  "ext": "mp4"},
    272: {"quality": "4320p", "type": "video",  "ext": "webm"},
    313: {"quality": "2160p", "type": "video",  "ext": "webm"},
    140: {"quality": "128kbps", "type": "audio", "ext": "m4a"},
    141: {"quality": "256kbps", "type": "audio", "ext": "m4a"},
    251: {"quality": "160kbps", "type": "audio", "ext": "webm"},
    250: {"quality": "70kbps",  "type": "audio", "ext": "webm"},
    249: {"quality": "50kbps",  "type": "audio", "ext": "webm"},
    139: {"quality": "48kbps",  "type": "audio", "ext": "m4a"},
}


def _parse_stream(fmt: dict) -> Optional[StreamInfo]:
    """Parse a single format dict into StreamInfo."""
    url = fmt.get("url")
    if not url:
        return None

    itag = int(fmt.get("itag", 0))
    mime_type = fmt.get("mimeType", "")
    vcodec = fmt.get("vcodec", "none")
    acodec = fmt.get("acodec", "none")

    if vcodec != "none" and acodec != "none":
        stream_type = "muxed"
    elif vcodec != "none":
        stream_type = "video"
    else:
        stream_type = "audio"

    ext_match = re.search(r"(?:video|audio)/(\w+)", mime_type)
    ext = ext_match.group(1) if ext_match else ITAG_MAP.get(itag, {}).get("ext", "mp4")

    codec = (vcodec if vcodec != "none" else acodec).split(".")[0]

    quality = (
        fmt.get("qualityLabel")
        or fmt.get("quality", "")
        or ITAG_MAP.get(itag, {}).get("quality", "unknown")
    )
    quality = re.sub(r"(\d+p)\d+", r"\1", quality).strip() or quality

    return StreamInfo(
        itag=itag,
        url=url,
        mime_type=mime_type,
        quality=quality,
        stream_type=stream_type,
        codec=codec,
        bitrate=int(fmt.get("bitrate", 0) or 0),
        filesize=int(fmt["contentLength"]) if fmt.get("contentLength") else None,
        width=fmt.get("width"),
        height=fmt.get("height"),
        fps=fmt.get("fps"),
        ext=ext,
    )


def _parse_streams(player_response: dict) -> list[StreamInfo]:
    """Parse and sort all available streams."""
    streaming_data = player_response.get("streamingData", {})
    raw_formats = (
        streaming_data.get("formats", []) +
        streaming_data.get("adaptiveFormats", [])
    )

    streams = [_parse_stream(fmt) for fmt in raw_formats]
    streams = [s for s in streams if s]

    streams.sort(key=lambda s: (
        {"muxed": 0, "video": 1, "audio": 2}.get(s.stream_type, 3),
        quality_sort_key(s.quality),
    ))

    return streams


# ─── Public API ─────────────────────────────────────────────────────────────

def get_video_info(url_or_id: str) -> VideoInfo:
    """Fetch video information and available streams."""
    video_id = None
    patterns = [
        r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, url_or_id)
        if m:
            video_id = m.group(1)
            break

    if not video_id:
        raise ValueError(
            f"Invalid YouTube URL or video ID: {url_or_id!r}\n"
            "Supported: https://youtube.com/watch?v=ID  |  youtu.be/ID  |  ID (11 chars)"
        )

    print(f"  -> Fetching video info: {video_id}")

    session = _create_session()

    last_error = ""
    for round_num in range(2):
        for client_name in _CLIENT_ORDER:
            try:
                player_response = _innertube_request(video_id, client_name, session)

                status = player_response.get("playabilityStatus", {})
                reason = status.get("status", "")
                if reason != "OK":
                    msg = status.get("reason") or (status.get("messages", [""])[0])
                    last_error = f"{reason}: {msg}"
                    print(f"  ! Client {client_name} blocked ({last_error}), trying next...")
                    continue

                streams = _parse_streams(player_response)
                if not streams:
                    last_error = "no streams"
                    print(f"  ! Client {client_name} returned no streams, trying next...")
                    continue

                if client_name != _CLIENT_ORDER[0]:
                    print(f"  -> Used fallback client: {client_name}")

                details = player_response.get("videoDetails", {})
                title = details.get("title", "Unknown Title")
                duration = int(details.get("lengthSeconds", 0))
                channel = details.get("author", "Unknown Channel")
                thumbnails = details.get("thumbnail", {}).get("thumbnails", [])
                thumbnail = thumbnails[-1]["url"] if thumbnails else ""

                return VideoInfo(
                    video_id=video_id,
                    title=title,
                    duration_seconds=duration,
                    channel=channel,
                    thumbnail=thumbnail,
                    streams=streams,
                )

            except RuntimeError as e:
                last_error = str(e)
                print(f"  ! Client {client_name} failed: {e}")
                continue

        if round_num == 0:
            print(f"  ! All clients failed, waiting 3s before final retry...")
            time.sleep(3)

    raise RuntimeError(
        f"Cannot download video {video_id}.\n"
        f"Last error: {last_error}\n"
        "The video may be private, DRM-protected, or region-locked."
    )


def get_best_stream(
    video_info: VideoInfo,
    quality: str = "best",
    audio_only: bool = False,
    prefer_mp4: bool = True,
) -> StreamInfo:
    """Select the best matching stream."""
    if audio_only:
        candidates = video_info.audio_streams()
        if not candidates:
            candidates = video_info.muxed_streams()
    else:
        candidates = video_info.muxed_streams() or video_info.video_streams()

    if not candidates:
        raise RuntimeError("No suitable streams available.")

    if prefer_mp4:
        mp4_candidates = [s for s in candidates if s.ext == "mp4"]
        if mp4_candidates:
            candidates = mp4_candidates

    if quality == "best":
        return candidates[0]
    if quality == "worst":
        return candidates[-1]

    for stream in candidates:
        if stream.quality == quality:
            return stream

    print(f"  ! Quality '{quality}' unavailable, using best: {candidates[0].quality}")
    return candidates[0]
