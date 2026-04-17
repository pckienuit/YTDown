#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YTDown - YouTube Video Downloader CLI
Phase 1: Muxed stream download (≤720p)

Usage:
    python ytdown.py <URL>
    python ytdown.py <URL> --list
    python ytdown.py <URL> --info
    python ytdown.py <URL> -q 720p
    python ytdown.py <URL> -o ./downloads
"""

import argparse
import io
import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.downloader import download_stream
from core.extractor import VideoInfo, get_best_stream, get_video_info
from core.utils import format_bytes, format_duration


# ─── Color + Style Helpers ────────────────────────────────────────────────────

class C:
    """ANSI color codes — auto-disabled on Windows without ANSI support."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
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


def _header():
    print(f"""
{C.CYAN}{C.BOLD}
  +===================================+
  |   YTDown - YouTube Downloader    |
  |   Phase 1 . Standard Library     |
  +===================================+{C.RESET}
""")


def _divider():
    print(f"{C.DIM}  {'─' * 60}{C.RESET}")


# ─── Display Functions ────────────────────────────────────────────────────────

def print_video_info(info: VideoInfo) -> None:
    """Print video metadata in a pretty format."""
    _divider()
    print(f"  {C.BOLD}>> {info.title}{C.RESET}")
    print(f"  {C.DIM}Channel: {info.channel}  |  Duration: {info.duration_str}{C.RESET}")
    print(f"  {C.DIM}URL: {info.url}{C.RESET}")
    _divider()


def print_stream_table(info: VideoInfo) -> None:
    """Print available streams as a formatted table."""
    streams = info.muxed_streams() + info.video_streams() + info.audio_streams()
    if not streams:
        print(f"  {C.YELLOW}No streams found.{C.RESET}")
        return

    col_w = [4, 10, 8, 16, 10, 6]
    headers = ["#", "Quality", "Format", "Codec", "Size", "Type"]

    def row(cells):
        return "  | " + " | ".join(
            str(c).ljust(w) for c, w in zip(cells, col_w)
        ) + " |"

    sep = "  +" + "+".join("-" * (w + 2) for w in col_w) + "+"

    print(f"\n  {C.BOLD}Available Streams:{C.RESET}")
    print(sep)
    print(f"{C.BOLD}{row(headers)}{C.RESET}")
    print(sep)
    for i, s in enumerate(streams, 1):
        size = f"~{format_bytes(s.filesize)}" if s.filesize else "?"
        print(row([i, s.quality, s.ext, s.codec[:16], size, s.stream_type]))
    print(sep)
    print()


# ─── CLI Argument Parsing ─────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ytdown",
        description="Download YouTube videos without third-party libraries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python ytdown.py https://youtube.com/watch?v=dQw4w9WgXcQ
  python ytdown.py https://youtu.be/dQw4w9WgXcQ --list
  python ytdown.py <URL> -q 720p -o ./downloads
  python ytdown.py <URL> --info
""",
    )
    p.add_argument("url", help="YouTube video URL or video ID")
    p.add_argument(
        "-q", "--quality",
        default="best",
        metavar="QUALITY",
        help='Quality to download: best | worst | 720p | 480p | 360p (default: best)',
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
        help="List all available streams without downloading",
    )
    p.add_argument(
        "--info",
        action="store_true",
        help="Show video info only (no streams, no download)",
    )
    return p


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _header()
    parser = build_parser()
    args = parser.parse_args()

    try:
        print(f"  {C.CYAN}Fetching video info for: {args.url}{C.RESET}")
        info = get_video_info(args.url)
        print_video_info(info)

        # --info: only show metadata
        if args.info:
            print(f"  {C.DIM}Streams: {len(info.streams)} total "
                  f"(video: {len(info.video_streams())}, "
                  f"audio: {len(info.audio_streams())}, "
                  f"muxed: {len(info.muxed_streams())}){C.RESET}")
            return

        # --list: show stream table
        if args.list:
            print_stream_table(info)
            return

        # Download
        print(f"  {C.CYAN}Selecting stream (quality={args.quality})...{C.RESET}")
        stream = get_best_stream(info, quality=args.quality)
        print(f"  {C.DIM}Selected: {stream.label()}{C.RESET}")

        print(f"\n  {C.GREEN}Starting download...{C.RESET}\n")

        output_path = download_stream(
            stream=stream,
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
