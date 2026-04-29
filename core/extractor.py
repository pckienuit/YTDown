"""
YouTube video information extractor.

Uses InnerTube API with ANDROID_VR client to get direct streaming URLs
without requiring signature cipher decryption.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# Ensure UTF-8 output on Windows (video titles may contain non-ASCII chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from core.utils import (
    ITAG_MAP,
    extract_video_id,
    format_duration,
    quality_sort_key,
    get_sapisidhash,
)

# Lazy-load HEADERS to avoid circular import
def _get_headers() -> dict:
    from core.utils import HEADERS
    return dict(HEADERS)


# ─── InnerTube Client Configs ────────────────────────────────────────────────
# Fallback order (best to worst bypass):
#   IOS → ANDROID → ANDROID_VR → TVHTML5 → WEB
#
# IOS / ANDROID give direct URLs without cipher and rarely trigger bot checks.
# TVHTML5 bypasses age-restriction but is being blocked more often.

_INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player"

_CLIENTS: dict[str, dict] = {
    # ── iOS app — best bypass, direct URLs, rarely flagged ─────────────────
    "IOS": {
        "client": {
            "clientName": "IOS",
            "clientVersion": "19.29.1",
            "deviceMake": "Apple",
            "deviceModel": "iPhone16,2",
            "osName": "iPhone",
            "osVersion": "17.5.1.21F90",
            "hl": "en",
            "gl": "US",
            "timeZone": "UTC",
            "utcOffsetMinutes": 0,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": (
                "com.google.ios.youtube/19.29.1 "
                "(iPhone16,2; U; CPU iPhone OS 17_5_1 like Mac OS X)"
            ),
            "X-YouTube-Client-Name": "5",
            "X-YouTube-Client-Version": "19.29.1",
        },
    },
    # ── Android app — direct URLs, good bypass ─────────────────────────────
    "ANDROID": {
        "client": {
            "clientName": "ANDROID",
            "clientVersion": "19.30.36",
            "androidSdkVersion": 34,
            "hl": "en",
            "gl": "US",
            "timeZone": "UTC",
            "utcOffsetMinutes": 0,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": (
                "com.google.android.youtube/19.30.36 "
                "(Linux; U; Android 14; en_US; Pixel 7 Build/UQ1A.240205.002) gzip"
            ),
            "X-YouTube-Client-Name": "3",
            "X-YouTube-Client-Version": "19.30.36",
            "Origin": "https://www.youtube.com",
        },
    },
    # ── Android VR — direct URLs, often bypasses age-restriction ───────────
    "ANDROID_VR": {
        "client": {
            "clientName": "ANDROID_VR",
            "clientVersion": "1.50.34",
            "androidSdkVersion": 32,
            "hl": "en",
            "gl": "US",
            "timeZone": "UTC",
            "utcOffsetMinutes": 0,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": (
                "com.google.android.apps.youtube.vr.oculus/1.50.34 "
                "(Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip"
            ),
            "X-YouTube-Client-Name": "ANDROID_VR",
            "X-YouTube-Client-Version": "1.50.34",
            "Origin": "https://www.youtube.com",
        },
    },
    # ── TV embed — bypasses age-restriction ────────────────────────────────
    "TVHTML5": {
        "client": {
            "clientName": "TVHTML5",
            "clientVersion": "1.20230619.04.00",
            "hl": "en",
            "timeZone": "UTC",
            "utcOffsetMinutes": 0,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/538.1 "
                "(KHTML, like Gecko) Version/6.0 TV Safari/538.1"
            ),
            "X-YouTube-Client-Name": "64",
            "X-YouTube-Client-Version": "1.20230619.04.00",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        },
    },
    # ── Android Embed — alternative age-restriction bypass ────────────────
    "ANDROID_EMBED": {
        "client": {
            "clientName": "ANDROID_EMBEDDED_PLAYER",
            "clientVersion": "19.30.36",
            "androidSdkVersion": 34,
            "hl": "en",
            "gl": "US",
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": (
                "com.google.android.youtube/19.30.36 "
                "(Linux; U; Android 14; en_US; Pixel 7 Build/UQ1A.240205.002) gzip"
            ),
            "X-YouTube-Client-Name": "3",
            "X-YouTube-Client-Version": "19.30.36",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        },
    },
    # ── Web browser — last resort, streams may need cipher ─────────────────
    "WEB": {
        "client": {
            "clientName": "WEB",
            "clientVersion": "2.20240726.00.00",
            "hl": "en",
            "timeZone": "UTC",
            "utcOffsetMinutes": 0,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": "2.20240726.00.00",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        },
    },
}

# Client fallback order — age-restriction bypassers first:
#   TVHTML5 → ANDROID_EMBED → IOS → ANDROID → ANDROID_VR → WEB
#
# TVHTML5 (client 64) and ANDROID_EMBED bypass age-restriction most effectively.
# IOS and ANDROID give direct URLs without cipher and rarely trigger bot checks.
# WEB is last resort (may need cipher).

_CLIENT_ORDER = ["TVHTML5", "ANDROID_EMBED", "IOS", "ANDROID", "ANDROID_VR", "WEB"]


# ─── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class StreamInfo:
    itag: int
    url: str
    mime_type: str
    quality: str
    stream_type: str        # "video" | "audio" | "muxed"
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


# ─── Visitor Data (anti-bot bypass) ──────────────────────────────────────────

_visitor_data_cache: str = ""

def _get_visitor_data() -> str:
    """
    Fetch visitorData from YouTube homepage ytcfg.
    This is a short-lived session token that tells YouTube we are a real browser session.
    Cached per process run.
    """
    global _visitor_data_cache
    if _visitor_data_cache:
        return _visitor_data_cache

    # Allow override via environment variable (useful for serverless deployments)
    env_visitor = os.environ.get("VISITOR_DATA")
    if env_visitor:
        _visitor_data_cache = env_visitor
        print("  [DEBUG] Using VISITOR_DATA from environment")
        return _visitor_data_cache

    # Detect serverless environment (Vercel, etc.)
    is_vercel = os.environ.get("VERCEL") == "1"

    # Try multiple approaches to fetch visitorData
    urls_to_try = [
        "https://www.youtube.com/",
        "https://www.youtube.com/?persist_gl=1&gl=US",
    ]

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]

    # Use shorter timeout in serverless environments
    timeout = 5 if is_vercel else 15

    for url in urls_to_try:
        for ua in user_agents:
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": ua,
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")

                # Try multiple extraction patterns
                patterns = [
                    r'"VISITOR_DATA"\s*:\s*"([^"]+)"',
                    r'"visitorData"\s*:\s*"([^"]+)"',
                    r'ytcfg\.set\(\s*{[^}]*"VISITOR_DATA"\s*:\s*"([^"]+)"',
                ]

                for pattern in patterns:
                    m = re.search(pattern, html)
                    if m:
                        _visitor_data_cache = m.group(1)
                        print(f"  [DEBUG] Successfully extracted visitorData from {url} using pattern {pattern[:30]}...")
                        return _visitor_data_cache

            except Exception as e:
                print(f"  [DEBUG] Attempt to fetch visitorData from {url} failed: {e}")
                continue

    if is_vercel:
        print("  [WARN] Vercel: Unable to fetch visitorData automatically. Set VISITOR_DATA env var as fallback.")
    else:
        print("  [DEBUG] All attempts to fetch visitorData failed")
    return ""


# ─── InnerTube API ────────────────────────────────────────────────────────────

def _innertube_player(video_id: str, client_name: str = "IOS") -> dict:
    """
    Call InnerTube /youtubei/v1/player with the specified client.
    Returns the raw player response JSON.

    Retries up to 2 times on HTTP 429 (rate limit) with exponential backoff.
    """
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            return _innertube_request(video_id, client_name)
        except RuntimeError as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in str(e) or "rate" in err_str or "too many requests" in err_str
            if is_rate_limit and attempt < max_retries:
                wait = 2 ** attempt
                print(f"  ! Rate limited (attempt {attempt + 1}/{max_retries + 1}), waiting {wait}s...")
                time.sleep(wait)
                continue
            raise


def _innertube_request(video_id: str, client_name: str) -> dict:
    """
    Single InnerTube API request. Extracted to separate function so retry logic
    in _innertube_player can wrap it cleanly.
    """
    client_cfg = _CLIENTS[client_name]
    _KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
    url  = f"{_INNERTUBE_URL}?key={_KEY}&prettyPrint=false"

    # Build context, injecting visitorData for bot-detection bypass
    visitor_data = _get_visitor_data()
    context: dict = {"client": dict(client_cfg["client"])}
    if visitor_data:
        context["client"]["visitorData"] = visitor_data

    payload = json.dumps({
        "videoId": video_id,
        "context": context,
    }).encode("utf-8")

    headers = dict(client_cfg["headers"])
    headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    if visitor_data:
        headers["X-Goog-Visitor-Id"] = visitor_data

    headers_base = _get_headers()
    if "Cookie" in headers_base:
        headers["Cookie"] = headers_base["Cookie"]
        sapisidhash = get_sapisidhash(headers_base["Cookie"])
        if sapisidhash:
            headers["Authorization"] = sapisidhash

    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RuntimeError("HTTP 429 Too Many Requests — rate limited by YouTube") from e
        raise RuntimeError(f"InnerTube API error: HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e




# ─── Playability Check ────────────────────────────────────────────────────────

def _check_playability(player_response: dict) -> tuple[bool, str]:
    """
    Check if the player response indicates the video is playable.

    Returns:
        (is_ok, error_message) — is_ok=True if video is playable.
    """
    status = player_response.get("playabilityStatus", {})
    reason = status.get("status", "")
    if reason == "OK":
        return True, ""

    message = status.get("reason") or (status.get("messages", [""])[0])
    error_map = {
        "LOGIN_REQUIRED":      "age-restricted or login required",
        "UNPLAYABLE":          f"unplayable: {message}",
        "ERROR":               f"error: {message}",
        "LIVE_STREAM_OFFLINE": "live stream is offline",
        "CONTENT_CHECK_REQUIRED": "content check required (age-restricted)",
        "AGE_CHECK_REQUIRED":  "age-restricted: authentication required",
    }
    err = error_map.get(reason, f"{reason}: {message}")
    return False, err


# ─── Stream Parsing ───────────────────────────────────────────────────────────

def _parse_stream(fmt: dict) -> Optional[StreamInfo]:
    """Parse a single format dict into StreamInfo."""
    url = fmt.get("url")
    if not url:
        return None  # Encrypted streams not supported without cipher

    itag = fmt.get("itag", 0)
    itag_info = ITAG_MAP.get(itag, {})
    mime_type = fmt.get("mimeType", "")

    # Determine stream type from mimeType content
    if "video" in mime_type and "audio" in mime_type:
        stream_type = "muxed"
    elif "video" in mime_type:
        stream_type = "video"
    else:
        stream_type = "audio"

    # Extract codec
    codec_match = re.search(r'codecs="([^"]+)"', mime_type)
    codec = (
        codec_match.group(1).split(",")[0].strip()
        if codec_match else itag_info.get("codec", "unknown")
    )

    # Extension
    ext_match = re.search(r"(?:video|audio)/(\w+)", mime_type)
    ext = ext_match.group(1) if ext_match else itag_info.get("ext", "mp4")

    quality = (
        fmt.get("qualityLabel")
        or itag_info.get("quality")
        or fmt.get("quality", "unknown")
    )
    # Strip frame-rate suffix for clean quality label (e.g. "1080p60" → "1080p")
    quality_clean = re.sub(r"(\d+p)\d+", r"\1", quality).strip() or quality

    return StreamInfo(
        itag=itag,
        url=url,
        mime_type=mime_type,
        quality=quality_clean,
        stream_type=stream_type,
        codec=codec,
        bitrate=fmt.get("bitrate", 0),
        filesize=int(fmt["contentLength"]) if fmt.get("contentLength") else None,
        width=fmt.get("width"),
        height=fmt.get("height"),
        fps=fmt.get("fps"),
        ext=ext,
    )


def _parse_streams(player_response: dict) -> list[StreamInfo]:
    """Parse and sort all available streams from the player response."""
    streaming_data = player_response.get("streamingData", {})
    raw_formats = (
        streaming_data.get("formats", []) +
        streaming_data.get("adaptiveFormats", [])
    )

    streams = []
    for fmt in raw_formats:
        stream = _parse_stream(fmt)
        if stream:
            streams.append(stream)

    # Sort: muxed first → video → audio, within each group highest quality first
    streams.sort(key=lambda s: (
        {"muxed": 0, "video": 1, "audio": 2}.get(s.stream_type, 3),
        quality_sort_key(s.quality),
    ))
    return streams


# ─── Public API ───────────────────────────────────────────────────────────────

def get_video_info(url_or_id: str) -> VideoInfo:
    """
    Fetch video information and available streams from YouTube.

    Tries multiple InnerTube clients in order (defined by _CLIENT_ORDER):
    1. TVHTML5       — bypasses age-restriction most effectively
    2. ANDROID_EMBED — alternative age-restriction bypass
    3. IOS           — direct URLs, rarely flagged by bot detection
    4. ANDROID       — direct URLs, good bypass
    5. ANDROID_VR    — direct URLs, may trigger bot check
    6. WEB           — last resort (may need cipher)

    On failure of all clients, retries once after a 3-second delay (graceful
    degradation) before raising an error.

    Args:
        url_or_id: YouTube URL or 11-character video ID.

    Returns:
        VideoInfo with metadata and list of available streams.

    Raises:
        ValueError: If URL/ID is invalid.
        RuntimeError: If video cannot be fetched with any client.
    """
    video_id = extract_video_id(url_or_id)
    if not video_id:
        raise ValueError(
            f"Invalid YouTube URL or video ID: {url_or_id!r}\n"
            "Supported: https://youtube.com/watch?v=ID  |  youtu.be/ID  |  ID (11 chars)"
        )

    print(f"  -> Fetching video info: {video_id}")

    # Outer loop: retry once with delay after all clients fail (graceful degradation)
    last_error = ""
    for round_num in range(2):
        for client_name in _CLIENT_ORDER:
            try:
                player_response = _innertube_player(video_id, client_name)
                is_ok, err = _check_playability(player_response)
                if not is_ok:
                    last_error = err
                    print(f"  ! Client {client_name} blocked ({err}), trying next...")
                    continue

                streams = _parse_streams(player_response)
                if not streams:
                    last_error = "no streams in response"
                    print(f"  ! Client {client_name} returned no streams, trying next...")
                    continue

                # Success — log only if we fell back from primary
                if client_name != _CLIENT_ORDER[0]:
                    print(f"  -> Used fallback client: {client_name}")

                details   = player_response.get("videoDetails", {})
                title     = details.get("title", "Unknown Title")
                duration  = int(details.get("lengthSeconds", 0))
                channel   = details.get("author", "Unknown Channel")
                thumbnails= details.get("thumbnail", {}).get("thumbnails", [])
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

        # All clients failed this round — wait and retry once
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
    """
    Select the best matching stream.

    Args:
        video_info: Parsed video information.
        quality: "best", "worst", or quality label like "720p", "1080p".
        audio_only: Return best audio stream if True.
        prefer_mp4: Prefer mp4 over webm when quality is equal.

    Returns:
        Best matching StreamInfo.
    """
    if audio_only:
        candidates = video_info.audio_streams()
        if not candidates:
            candidates = video_info.muxed_streams()
    else:
        # Prefer muxed (has audio), fallback to video-only
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

    # Match by quality label
    for stream in candidates:
        if stream.quality == quality:
            return stream

    # Fallback
    print(f"  ! Quality '{quality}' unavailable, using best: {candidates[0].quality}")
    return candidates[0]
