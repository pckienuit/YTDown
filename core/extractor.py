"""
YouTube video information extractor.

Uses InnerTube API with ANDROID_VR client to get direct streaming URLs
without requiring signature cipher decryption.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from core.utils import (
    ITAG_MAP,
    extract_video_id,
    format_duration,
    quality_sort_key,
)


# ─── InnerTube Client Config ─────────────────────────────────────────────────
# ANDROID_VR returns direct URLs without signatureCipher

_INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player"

_ANDROID_VR_CLIENT = {
    "clientName": "ANDROID_VR",
    "clientVersion": "1.60.19",
    "androidSdkVersion": 32,
    "hl": "en",
    "timeZone": "UTC",
    "utcOffsetMinutes": 0,
}

_ANDROID_VR_UA = (
    "com.google.android.apps.youtube.vr.oculus/1.60.19 "
    "(Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip"
)

_INNERTUBE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": _ANDROID_VR_UA,
    "X-YouTube-Client-Name": "ANDROID_VR",
    "X-YouTube-Client-Version": "1.60.19",
    "Origin": "https://www.youtube.com",
    "Referer": "https://www.youtube.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


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


# ─── InnerTube API ────────────────────────────────────────────────────────────

def _innertube_player(video_id: str) -> dict:
    """
    Call InnerTube /youtubei/v1/player with ANDROID_VR client.
    Returns the player response JSON (includes direct streaming URLs).
    """
    payload = json.dumps({
        "videoId": video_id,
        "context": {
            "client": _ANDROID_VR_CLIENT,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        _INNERTUBE_URL,
        data=payload,
        headers=_INNERTUBE_HEADERS,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"InnerTube API error: HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e


# ─── Playability Check ────────────────────────────────────────────────────────

def _check_playability(player_response: dict) -> None:
    """Raise if video is not playable."""
    status = player_response.get("playabilityStatus", {})
    reason = status.get("status", "")
    if reason == "OK":
        return

    message = status.get("reason") or status.get("messages", ["Unknown reason"])[0]
    error_map = {
        "LOGIN_REQUIRED": "Video requires login (age-restricted or private)",
        "UNPLAYABLE": f"Video is unplayable: {message}",
        "ERROR": f"Video error: {message}",
        "LIVE_STREAM_OFFLINE": "Live stream is offline",
        "CONTENT_CHECK_REQUIRED": "Content check required (age-restricted)",
    }
    raise RuntimeError(error_map.get(reason, f"Cannot play video ({reason}): {message}"))


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

    Uses InnerTube API with ANDROID_VR client for direct URLs (no cipher needed).

    Args:
        url_or_id: YouTube URL or 11-character video ID.

    Returns:
        VideoInfo with metadata and list of available streams.

    Raises:
        ValueError: If URL/ID is invalid.
        RuntimeError: If video cannot be fetched or is unavailable.
    """
    video_id = extract_video_id(url_or_id)
    if not video_id:
        raise ValueError(
            f"Invalid YouTube URL or video ID: {url_or_id!r}\n"
            "Supported: https://youtube.com/watch?v=ID  |  youtu.be/ID  |  ID (11 chars)"
        )

    print(f"  -> Fetching video info: {video_id}")
    player_response = _innertube_player(video_id)
    _check_playability(player_response)

    details = player_response.get("videoDetails", {})
    title = details.get("title", "Unknown Title")
    duration = int(details.get("lengthSeconds", 0))
    channel = details.get("author", "Unknown Channel")

    # Best available thumbnail
    thumbnails = details.get("thumbnail", {}).get("thumbnails", [])
    thumbnail = thumbnails[-1]["url"] if thumbnails else ""

    streams = _parse_streams(player_response)
    if not streams:
        raise RuntimeError(
            "No downloadable streams found. "
            "The video may be DRM-protected, private, or region-locked."
        )

    return VideoInfo(
        video_id=video_id,
        title=title,
        duration_seconds=duration,
        channel=channel,
        thumbnail=thumbnail,
        streams=streams,
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
