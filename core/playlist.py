"""
YouTube Playlist extractor — Phase 4.

Fetches playlist metadata and video list by parsing ytInitialData from
the playlist page HTML. No API key or third-party library needed.
Supports paginated playlists (> 100 videos) via InnerTube continuation.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urlparse

# ─── HTTP Headers ─────────────────────────────────────────────────────────────

_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cookie": (
        "SOCS=CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjUwNDE1LjA1X3AwGgJlbiACGgYIgJb5vAY"
    ),
}

_INNERTUBE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "X-YouTube-Client-Name": "1",
    "X-YouTube-Client-Version": "2.20240726.00.00",
    "Origin": "https://www.youtube.com",
    "Referer": "https://www.youtube.com/",
}


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class PlaylistEntry:
    """Lightweight representation of one video in a playlist."""
    video_id:  str
    title:     str
    duration:  int      # seconds (0 if unknown)
    thumbnail: str
    channel:   str
    index:     int      # 1-based position in playlist


@dataclass
class PlaylistInfo:
    playlist_id: str
    title:       str
    channel:     str
    video_count: int
    thumbnail:   str
    url:         str
    entries:     list[PlaylistEntry] = field(default_factory=list)


# ─── URL Utilities ────────────────────────────────────────────────────────────

def is_playlist_url(url: str) -> bool:
    """Return True if the URL contains a playlist ID (list= param)."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    return "list" in qs and bool(qs["list"][0])


def extract_playlist_id(url: str) -> Optional[str]:
    """Extract playlist ID from a YouTube URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    ids = qs.get("list", [])
    return ids[0] if ids else None


# ─── Page Fetching ────────────────────────────────────────────────────────────

def _fetch_playlist_page(playlist_id: str) -> str:
    """Fetch the playlist page HTML."""
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    from core.utils import HEADERS
    headers = dict(_PAGE_HEADERS)
    if "Cookie" in HEADERS:
        headers["Cookie"] = HEADERS["Cookie"]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching playlist page") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e


def _extract_initial_data(html: str) -> dict:
    """Extract ytInitialData JSON embedded in the HTML page."""
    # Method 1: var ytInitialData = {...};
    start = html.find("var ytInitialData = ")
    if start != -1:
        start += len("var ytInitialData = ")
        end = html.find(";</script>", start)
        if end != -1:
            try:
                return json.loads(html[start:end])
            except json.JSONDecodeError:
                pass

    # Method 2: window["ytInitialData"] = {...};
    start = html.find('window["ytInitialData"] = ')
    if start != -1:
        start += len('window["ytInitialData"] = ')
        end = html.find(";</script>", start)
        if end != -1:
            try:
                return json.loads(html[start:end])
            except json.JSONDecodeError:
                pass

    raise RuntimeError("Could not extract ytInitialData from the playlist page. "
                       "The playlist may be private or the page format changed.")


# ─── InnerTube Continuation ───────────────────────────────────────────────────

def _continue_playlist(token: str) -> dict:
    """Fetch the next page of playlist items via InnerTube continuation."""
    url  = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"

    from core.extractor import _get_visitor_data
    from core.utils import HEADERS, get_sapisidhash
    headers = dict(_INNERTUBE_HEADERS)
    if "Cookie" in HEADERS:
        headers["Cookie"] = HEADERS["Cookie"]
        sapisidhash = get_sapisidhash(HEADERS["Cookie"])
        if sapisidhash:
            headers["Authorization"] = sapisidhash

    visitor_data = _get_visitor_data()
    body = json.dumps({
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240726.00.00",
                "hl": "en",
                "gl": "US",
                "visitorData": visitor_data or "",
            }
        },
        "continuation": token,
    }).encode("utf-8")
    if visitor_data:
        headers["X-Goog-Visitor-Id"] = visitor_data
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


# ─── Parsing Helpers ──────────────────────────────────────────────────────────

def _parse_duration_text(text: str) -> int:
    """Convert 'H:MM:SS' or 'M:SS' to seconds."""
    if not text:
        return 0
    parts = [int(p) for p in text.strip().split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    return 0


def _best_thumbnail(thumbnails: list) -> str:
    """Pick the highest-resolution thumbnail URL."""
    if not thumbnails:
        return ""
    return max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0)).get("url", "")


def _find_node(data, key: str):
    """BFS search for the first node matching key in nested dict/list."""
    queue = [data]
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            if key in node:
                return node[key]
            queue.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            queue.extend(item for item in node if isinstance(item, (dict, list)))
    return None


def _get_continuation_token(data) -> Optional[str]:
    """Find the first continuationCommand token in a nested structure."""
    if isinstance(data, dict):
        # Check for continuationItemRenderer directly
        if "continuationItemRenderer" in data:
            try:
                return (
                    data["continuationItemRenderer"]
                    ["continuationEndpoint"]["continuationCommand"]["token"]
                )
            except (KeyError, TypeError):
                pass
        for v in data.values():
            t = _get_continuation_token(v)
            if t:
                return t
    elif isinstance(data, list):
        for item in data:
            t = _get_continuation_token(item)
            if t:
                return t
    return None


def _parse_playlist_videos(items: list) -> list[PlaylistEntry]:
    """Parse playlistVideoRenderer items into PlaylistEntry objects."""
    entries = []
    for item in items:
        r = item.get("playlistVideoRenderer", {})
        if not r:
            continue

        video_id = r.get("videoId", "")
        if not video_id:
            continue

        title = (
            r.get("title", {}).get("runs", [{}])[0].get("text", "")
            or r.get("title", {}).get("simpleText", "Unknown")
        )
        idx = int(r.get("index", {}).get("simpleText", 0) or 0)

        dur_text  = (r.get("lengthText", {}).get("simpleText", "")
                     or r.get("lengthText", {}).get("runs", [{}])[0].get("text", ""))
        duration  = _parse_duration_text(dur_text)
        thumbs    = r.get("thumbnail", {}).get("thumbnails", [])
        thumbnail = _best_thumbnail(thumbs) or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
        channel   = r.get("shortBylineText", {}).get("runs", [{}])[0].get("text", "")

        entries.append(PlaylistEntry(
            video_id=video_id, title=title, duration=duration,
            thumbnail=thumbnail, channel=channel, index=idx,
        ))
    return entries


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_playlist_info(playlist_id: str, max_videos: int = 500) -> PlaylistInfo:
    """
    Fetch playlist metadata and entries from YouTube.

    Uses HTML page + ytInitialData parsing. No API key required.
    Follows continuation tokens for playlists > 100 videos.
    """
    print(f"  -> Fetching playlist: {playlist_id}")
    html = _fetch_playlist_page(playlist_id)
    data = _extract_initial_data(html)

    # ── Metadata ──────────────────────────────────────────────────────────────
    title   = ""
    channel = ""

    try:
        sidebar_items = data["sidebar"]["playlistSidebarRenderer"]["items"]
        for item in sidebar_items:
            pri = item.get("playlistSidebarPrimaryInfoRenderer", {})
            if pri:
                title = (pri.get("title", {}).get("runs", [{}])[0].get("text", "")
                         or pri.get("title", {}).get("simpleText", ""))
            sec = item.get("playlistSidebarSecondaryInfoRenderer", {})
            if sec:
                owner = sec.get("videoOwner", {}).get("videoOwnerRenderer", {})
                channel = owner.get("title", {}).get("runs", [{}])[0].get("text", "")
    except (KeyError, IndexError, TypeError):
        pass

    if not title:
        title = (data.get("metadata", {}).get("playlistMetadataRenderer", {})
                 .get("title", "Unknown Playlist"))
    if not channel:
        channel = (data.get("microformat", {}).get("microformatDataRenderer", {})
                   .get("ownerChannelName", ""))

    # ── Video list ────────────────────────────────────────────────────────────
    all_entries: list[PlaylistEntry] = []

    video_list_renderer = _find_node(data, "playlistVideoListRenderer")
    if not video_list_renderer:
        raise RuntimeError(
            f"Playlist '{playlist_id}' is private, empty, or not accessible."
        )

    items = video_list_renderer.get("contents", [])
    all_entries.extend(_parse_playlist_videos(items))
    token = _get_continuation_token(video_list_renderer)

    # ── Continuation pages ────────────────────────────────────────────────────
    while token and len(all_entries) < max_videos:
        print(f"  -> Loading more videos ({len(all_entries)} so far)...")
        resp = _continue_playlist(token)
        if not resp:
            break

        cont_items = []
        try:
            for action in resp.get("onResponseReceivedActions", []):
                cont_items = action.get("appendContinuationItemsAction", {}).get("continuationItems", [])
                if cont_items:
                    break
        except Exception:
            pass

        if not cont_items:
            break

        new = _parse_playlist_videos(cont_items)
        if not new:
            break
        all_entries.extend(new)
        token = _get_continuation_token(resp)

    # Re-number any 0-indexed entries
    for i, e in enumerate(all_entries, 1):
        if e.index == 0:
            e.index = i

    playlist_thumb = all_entries[0].thumbnail if all_entries else ""
    video_count    = len(all_entries)
    print(f"  -> Playlist: '{title}' — {video_count} videos")

    return PlaylistInfo(
        playlist_id = playlist_id,
        title       = title,
        channel     = channel,
        video_count = video_count,
        thumbnail   = playlist_thumb,
        url         = f"https://www.youtube.com/playlist?list={playlist_id}",
        entries     = all_entries,
    )


def get_playlist_info(url: str) -> PlaylistInfo:
    """
    Fetch playlist info from a YouTube playlist URL.

    Raises:
        ValueError: If the URL has no playlist ID.
        RuntimeError: If the fetch fails.
    """
    playlist_id = extract_playlist_id(url)
    if not playlist_id:
        raise ValueError(f"No playlist ID found in URL: {url!r}")
    return fetch_playlist_info(playlist_id)
