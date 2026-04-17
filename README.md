# YTDown — YouTube Downloader (Python Standard Library)

A high-performance YouTube downloader built entirely using the Python Standard Library — **0 third-party packages required**. It features an interactive CLI, a stunning Web UI (Dark Glassmorphism), blazing-fast parallel downloads, and the most robust anti-bot detection bypass using client pooling and `visitorData` injection.

## ⭐ Key Features

- **Blazing Fast**: Uses up to 4 parallel HTTP connections for video chunking, achieving max bandwidth (7-10+ MB/s) entirely through Python's `urllib`.
- **Anti-Bot Bypass**: Iterates through 5 YouTube Internal API clients (`IOS` → `ANDROID` → `ANDROID_VR` → `TVHTML5` → `WEB`) and uses live `visitorData` payloads to seamlessly bypass YouTube's strict bot detection.
- **Zero Dependencies**: Uses pure Python out-of-the-box (`json`, `urllib`, `threading`, `re`).
- **Web UI**: Modern single-page web app with Server-Sent Events (SSE) for real-time progress bars, playlist selections, and high-fidelity aesthetics.
- **Playlist Support**: Pass a playlist URL to parse and bulk-download videos/audio natively.
- **FFmpeg Integration**: Auto-detects `ffmpeg` via Winget/system PATH. Automatically merges the highest quality video and audio streams seamlessly. Graceful fallback on machines without FFmpeg.

---

## 🚀 Quick Start

### 1. Web UI (Recommended)
Start the local server and open your browser:
```bash
python server.py
# Open http://localhost:8080
```

### 2. CLI Usage
```bash
# Show video info
python ytdown.py <URL> --info

# List all available streams (144p → 4K + audio)
python ytdown.py <URL> --list

# Download best quality (auto-merge with FFmpeg if available)
python ytdown.py <URL>

# Download specific quality
python ytdown.py <URL> -q 1080p

# Download audio only as MP3 (requires FFmpeg)
python ytdown.py <URL> -a

# Download audio only as M4A (no FFmpeg needed)
python ytdown.py <URL> -a --af m4a

# Download an entire playlist to a custom folder
python ytdown.py <PLAYLIST_URL> -o ./my-playlist
```

---

## 📁 Project Structure

```
YTDown/
├── ytdown.py          # CLI entry point
├── server.py          # Web server (SSE, REST APIs)
├── core/
│   ├── __init__.py
│   ├── utils.py       # Helpers, ITAG map, formatting
│   ├── extractor.py   # InnerTube API, Multiplexed Client Fallback, Bot Bypass
│   ├── downloader.py  # Multi-threaded concurrent chunk downloader (4x speed)
│   ├── merger.py      # FFmpeg detection, video+audio muxing
│   └── playlist.py    # Playlist scraping via YouTube initial data
├── static/
│   ├── index.html     # Web UI single-page app
│   ├── style.css      # Dark glassmorphism design system
│   └── app.js         # Frontend logic, SSE progress listeners
└── downloads/         # Output directory (auto-created)
```

---

## ⚙️ Requirements

- **Python 3.10+** — strictly standard library only, no `pip install` needed.
- **FFmpeg** (optional but highly recommended) — required for:
  - Downloading and merging high-resolution video streams (1080p, 1440p, 4K) where YouTube separates video and audio tracks.
  - Converting audio downloads directly to `MP3`.
  - Fallback logic: Without FFmpeg, downloads gracefully degrade to 720p muxed streams (or download audio/video as separate independent files).

#### Install FFmpeg (Windows via winget)
```bash
winget install ffmpeg
```

---

## 🛠️ Technical Details

- **Multi-Client Fallback Network**: YTDown handles restricted videos by cycling through `IOS`, `ANDROID`, `ANDROID_VR`, `TVHTML5`, and `WEB` client endpoints using the `/youtubei/v1/player` InnerTube API.
- **VisitorData Token Exchange**: Fetching a pre-flight token mimicking a real device session to bypass HTTP 400 preconditions and "Sign in to confirm you're not a bot" errors.
- **Parallel Chunked Engine**: Implements HTTP Range byte-requests, breaking files >5MB into 8MB chunks downloaded concurrently over a thread pool. This single-handedly circumvents classic YouTube CDN stream throttling.
- **Real-Time Pub/Sub**: The backend `server.py` routes terminal stdout byte-counts directly into a `queue.Queue()`, beaming it as SSE payloads to the browser for sub-millisecond precision progress bars.
