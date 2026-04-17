# YTDown — YouTube Downloader (Python Standard Library)

## Quick Start

```bash
# Show video info
python ytdown.py <URL> --info

# List available streams
python ytdown.py <URL> --list

# Download best quality
python ytdown.py <URL>

# Download specific quality
python ytdown.py <URL> -q 720p

# Download to custom folder
python ytdown.py <URL> -o ./my-videos
```

## Project Structure

```
YTDown/
├── ytdown.py          # CLI entry point
├── server.py          # Web server (Phase 4)
├── core/
│   ├── __init__.py
│   ├── utils.py       # Helpers, constants
│   ├── extractor.py   # YouTube data extraction
│   ├── cipher.py      # Signature decryption (Phase 2)
│   ├── downloader.py  # File download engine
│   ├── merger.py      # FFmpeg merge (Phase 3)
│   └── playlist.py    # Playlist support (Phase 5)
├── static/            # Web UI (Phase 4)
└── downloads/         # Output directory
```

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Core extraction + Basic CLI | ✅ Complete |
| 2 | Cipher decryption + Adaptive streams | 🔲 Pending |
| 3 | FFmpeg merge + Audio extraction | 🔲 Pending |
| 4 | Web UI | 🔲 Pending |
| 5 | Playlist support | 🔲 Pending |

## Requirements

- Python 3.10+ (standard library only)
- FFmpeg (optional, required for 1080p+ merge — Phase 3)

## Notes

- Phase 1 supports muxed streams up to 720p
- Phase 2 will add cipher decryption for 1080p/4K adaptive streams
- Downloads resume automatically on failure
