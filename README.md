# YTDown — YouTube Downloader (Python Standard Library)

No third-party packages required. Uses YouTube's InnerTube API with ANDROID_VR client.

## Quick Start

### CLI
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

# Custom output folder
python ytdown.py <URL> -q 720p -o ./my-videos
```

### Web UI
```bash
python server.py
# Open http://localhost:8080
```

## Project Structure

```
YTDown/
├── ytdown.py          # CLI entry point
├── server.py          # Web server (Phase 3)
├── core/
│   ├── __init__.py
│   ├── utils.py       # Helpers, ITAG map, constants
│   ├── extractor.py   # InnerTube API + stream parser
│   ├── cipher.py      # Cipher stub (not needed with ANDROID_VR client)
│   ├── downloader.py  # Chunked download + progress + smart merge routing
│   ├── merger.py      # FFmpeg detection + video+audio merge + MP3 convert
│   └── playlist.py    # Playlist support (Phase 5)
├── static/
│   ├── index.html     # Web UI single-page app
│   ├── style.css      # Dark glassmorphism design
│   └── app.js         # Frontend logic (vanilla JS)
└── downloads/         # Output directory (auto-created)
```

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Core extraction + Basic CLI | ✅ Complete |
| 2 | FFmpeg merge + Audio extraction | ✅ Complete |
| 3 | Web UI (dark glassmorphism) | ✅ Complete |
| 4 | Playlist support | 🔲 Pending |

## Requirements

- **Python 3.10+** — standard library only, no pip install needed
- **FFmpeg** (optional) — required for:
  - Merging 1080p+ video+audio streams
  - Converting audio to MP3
  - Without FFmpeg: video streams download without audio

## Install FFmpeg (optional)

```bash
# Windows (winget)
winget install ffmpeg

# Windows (manual)
# Download from https://ffmpeg.org/download.html
# Add to PATH or place in C:\ffmpeg\bin\

# macOS
brew install ffmpeg
```

## Supported Formats

| Quality | Type | Notes |
|---------|------|-------|
| 2160p (4K) | video-only | Requires FFmpeg to merge audio |
| 1440p | video-only | Requires FFmpeg to merge audio |
| 1080p | video-only | Requires FFmpeg to merge audio |
| 720p | video-only | Requires FFmpeg to merge audio |
| 480p, 360p, 240p, 144p | video-only | Requires FFmpeg to merge audio |
| 128kbps, 160kbps | audio-only | M4A native / MP3 via FFmpeg |

## Technical Notes

- Uses **InnerTube API** (`/youtubei/v1/player`) with `ANDROID_VR` client
- ANDROID_VR client returns **direct streaming URLs** — no signature cipher needed
- All downloads support **resume** via HTTP Range header
- Downloads run in **background threads** (web server supports concurrent downloads)
