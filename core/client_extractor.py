"""
Client-side YouTube data extraction via browser.
This runs in the browser to bypass serverless outbound restrictions.
"""

import re
import base64
from dataclasses import dataclass, field
from typing import Optional


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
        from core.utils import format_duration
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


# ─── Player Response Parsing ─────────────────────────────────────────────────

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


def parse_stream(fmt: dict) -> Optional[StreamInfo]:
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


def parse_player_response(player_response: dict, video_id: str) -> VideoInfo:
    """Parse player response into VideoInfo."""
    from core.utils import format_duration, quality_sort_key

    details = player_response.get("videoDetails", {})
    title = details.get("title", "Unknown Title")
    duration = int(details.get("lengthSeconds", 0))
    channel = details.get("author", "Unknown Channel")
    thumbnails = details.get("thumbnail", {}).get("thumbnails", [])
    thumbnail = thumbnails[-1]["url"] if thumbnails else ""

    streaming_data = player_response.get("streamingData", {})
    raw_formats = (
        streaming_data.get("formats", []) +
        streaming_data.get("adaptiveFormats", [])
    )

    streams = [parse_stream(fmt) for fmt in raw_formats]
    streams = [s for s in streams if s]

    streams.sort(key=lambda s: (
        {"muxed": 0, "video": 1, "audio": 2}.get(s.stream_type, 3),
        quality_sort_key(s.quality),
    ))

    return VideoInfo(
        video_id=video_id,
        title=title,
        duration_seconds=duration,
        channel=channel,
        thumbnail=thumbnail,
        streams=streams,
    )


def get_video_info_from_client_data(data: dict) -> VideoInfo:
    """
    Create VideoInfo from client-side extracted data.
    data format: { video_id, title, duration, channel, thumbnail, streamingData }
    """
    video_id = data.get("video_id", "")
    title = data.get("title", "Unknown Title")
    duration = int(data.get("duration", 0))
    channel = data.get("channel", "Unknown Channel")
    thumbnail = data.get("thumbnail", "")
    streaming_data = data.get("streamingData", {})

    raw_formats = (
        streaming_data.get("formats", []) +
        streaming_data.get("adaptiveFormats", [])
    )

    streams = [parse_stream(fmt) for fmt in raw_formats]
    streams = [s for s in streams if s]

    return VideoInfo(
        video_id=video_id,
        title=title,
        duration_seconds=duration,
        channel=channel,
        thumbnail=thumbnail,
        streams=streams,
    )
