#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YTDown - YouTube Video Downloader CLI
Phase 2: FFmpeg merge + audio extraction

Usage:
    python ytdown.py <URL>
    python ytdown.py <URL> --list
    python ytdown.py <URL> --info
    python ytdown.py <URL> -q 1080p          # Auto-merge with FFmpeg
    python ytdown.py <URL> -a                # Audio only (MP3)
    python ytdown.py <URL> -a --af m4a       # Audio only (native m4a)
    python ytdown.py <URL> -q 720p -o ./dir
"""

import argparse
import io
import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.downloader import download_with_audio, download_stream
from core.extractor import VideoInfo, get_best_stream, get_video_info
from core.merger import find_ffmpeg, get_ffmpeg_version, is_ffmpeg_available
from core.utils import format_bytes, format_duration


# ─── Color Helpers ────────────────────────────────────────────────────────────

class C:
    """ANSI color codes — auto-enabled on Windows via SetConsoleMode."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7
        )
        _enabled = True
    except Exception:
        _enabled = os.environ.get("TERM") is not None

    RESET  = "\033[0m"  if _enabled else ""
    BOLD   = "\033[1m"  if _enabled else ""
    CYAN   = "\033[96m" if _enabled else ""
    GREEN  = "\033[92m" if _enabled else ""
    YELLOW = "\033[93m" if _enabled else ""
    RED    = "\033[91m" if _enabled else ""
    DIM    = "\033[2m"  if _enabled else ""
    MAGENTA= "\033[95m" if _enabled else ""


def _header():
    print(f"""
{C.CYAN}{C.BOLD}
  +===================================+
  |   YTDown - YouTube Downloader    |
  |   Phase 2 . FFmpeg + Audio       |
  +===================================+{C.RESET}
""")


def _divider():
    print(f"{C.DIM}  {'─' * 60}{C.RESET}")


# ─── Display Functions ────────────────────────────────────────────────────────

def print_ffmpeg_status() -> None:
    """Print FFmpeg availability status."""
    version = get_ffmpeg_version()
    if version:
        ffmpeg_path = find_ffmpeg()
        print(f"  {C.GREEN}FFmpeg: v{version}{C.RESET}  {C.DIM}({ffmpeg_path}){C.RESET}")
    else:
        print(
            f"  {C.YELLOW}FFmpeg: not found{C.RESET}  "
            f"{C.DIM}(max quality: best available video-only stream){C.RESET}\n"
            f"  {C.DIM}Install: https://ffmpeg.org/download.html  |  winget install ffmpeg{C.RESET}"
        )


def print_video_info(info: VideoInfo) -> None:
    """Print video metadata."""
    _divider()
    print(f"  {C.BOLD}>> {info.title}{C.RESET}")
    print(f"  {C.DIM}Channel: {info.channel}  |  Duration: {info.duration_str}{C.RESET}")
    print(f"  {C.DIM}URL: {info.url}{C.RESET}")
    _divider()


def print_stream_table(info: VideoInfo) -> None:
    """Print all available streams as a formatted table."""
    streams = info.muxed_streams() + info.video_streams() + info.audio_streams()
    if not streams:
        print(f"  {C.YELLOW}No streams found.{C.RESET}")
        return

    col_w = [4, 10, 8, 20, 10, 6]
    headers = ["#", "Quality", "Format", "Codec", "Size", "Type"]

    def row(cells):
        return "  | " + " | ".join(
            str(c).ljust(w) for c, w in zip(cells, col_w)
        ) + " |"

    sep = "  +" + "+".join("-" * (w + 2) for w in col_w) + "+"

    ffmpeg_ok = is_ffmpeg_available()

    print(f"\n  {C.BOLD}Available Streams:{C.RESET}")
    if not ffmpeg_ok:
        print(f"  {C.DIM}(Install FFmpeg to merge adaptive video+audio for 1080p+){C.RESET}")
    print(sep)
    print(f"{C.BOLD}{row(headers)}{C.RESET}")
    print(sep)

    for i, s in enumerate(streams, 1):
        size = f"~{format_bytes(s.filesize)}" if s.filesize else "?"
        # Color-code by type
        if s.stream_type == "muxed":
            color = C.GREEN
        elif s.stream_type == "audio":
            color = C.MAGENTA
        else:
            color = ""
        reset = C.RESET if color else ""
        print(f"{color}{row([i, s.quality, s.ext, s.codec[:20], size, s.stream_type])}{reset}")

    print(sep)
    print()


# ─── CLI Argument Parsing ─────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ytdown",
        description="Download YouTube videos — no third-party libraries required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python ytdown.py <URL>                    Download best video (auto-merge with FFmpeg)
  python ytdown.py <URL> --list             Show all available streams
  python ytdown.py <URL> --info             Show video info only
  python ytdown.py <URL> -q 1080p          Download 1080p (auto-merge audio if FFmpeg found)
  python ytdown.py <URL> -q 720p -o ./dir  Download 720p to custom folder
  python ytdown.py <URL> -a                Download audio only as MP3
  python ytdown.py <URL> -a --af m4a       Download audio only as M4A (no FFmpeg needed)
""",
    )
    p.add_argument("url", help="YouTube video URL or 11-char video ID")
    p.add_argument(
        "-q", "--quality",
        default="best",
        metavar="QUALITY",
        help="Quality: best | worst | 2160p | 1440p | 1080p | 720p | 480p | 360p | 240p | 144p",
    )
    p.add_argument(
        "-o", "--output",
        default="downloads",
        metavar="DIR",
        help="Output directory (default: ./downloads)",
    )
    p.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all available streams and exit",
    )
    p.add_argument(
        "--info",
        action="store_true",
        help="Show video info only (no download)",
    )
    p.add_argument(
        "-a", "--audio",
        action="store_true",
        help="Download audio only",
    )
    p.add_argument(
        "--af", "--audio-format",
        dest="audio_format",
        default="mp3",
        choices=["mp3", "m4a", "copy"],
        metavar="FORMAT",
        help="Audio format when -a is used: mp3 | m4a | copy (default: mp3)",
    )
    return p


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _header()
    print_ffmpeg_status()
    print()

    parser = build_parser()
    args = parser.parse_args()

    try:
        print(f"  {C.CYAN}Fetching video info: {args.url}{C.RESET}")
        info = get_video_info(args.url)
        print_video_info(info)

        # --info mode
        if args.info:
            vs = len(info.video_streams())
            aus = len(info.audio_streams())
            ms = len(info.muxed_streams())
            print(f"  {C.DIM}Streams: {len(info.streams)} total  "
                  f"(video: {vs}, audio: {aus}, muxed: {ms}){C.RESET}\n")
            return

        # --list mode
        if args.list:
            print_stream_table(info)
            return

        # Audio-only mode
        if args.audio:
            print(f"\n  {C.CYAN}Audio-only mode — format: {args.audio_format}{C.RESET}\n")
            # Pass a dummy stream; download_with_audio handles audio selection internally
            dummy_stream = info.audio_streams()[0] if info.audio_streams() else None
            if not dummy_stream:
                raise RuntimeError("No audio streams available for this video.")
            output_path = download_with_audio(
                video_stream=dummy_stream,
                video_info=info,
                output_dir=args.output,
                audio_only=True,
                audio_format=args.audio_format,
            )
            print(f"\n  {C.GREEN}{C.BOLD}[OK] Audio saved:{C.RESET}")
            print(f"  {C.DIM}{output_path}{C.RESET}\n")
            return

        # Video download
        print(f"  {C.CYAN}Selecting stream (quality={args.quality})...{C.RESET}")
        stream = get_best_stream(info, quality=args.quality, prefer_mp4=True)
        print(f"  {C.DIM}Selected: {stream.label()}{C.RESET}")

        if stream.stream_type == "video" and is_ffmpeg_available():
            print(f"  {C.DIM}(Will merge with best audio via FFmpeg){C.RESET}")
        elif stream.stream_type == "video" and not is_ffmpeg_available():
            print(f"  {C.YELLOW}  FFmpeg not found — video will have no audio.{C.RESET}")

        print(f"\n  {C.GREEN}Starting download...{C.RESET}\n")

        output_path = download_with_audio(
            video_stream=stream,
            video_info=info,
            output_dir=args.output,
        )

        print(f"\n  {C.GREEN}{C.BOLD}[OK] Download complete!{C.RESET}")
        print(f"  {C.DIM}Saved: {output_path}{C.RESET}\n")

    except (ValueError, RuntimeError) as e:
        print(f"\n  {C.RED}[ERROR] {e}{C.RESET}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}[!] Cancelled by user.{C.RESET}\n")
        sys.exit(130)


if __name__ == "__main__":
    main()
