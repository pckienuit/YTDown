#!/usr/bin/env python3
"""
Helper script to extract YouTube authentication credentials for Vercel deployment.

This script helps you obtain two environment variables:
1. VISITOR_DATA - A short-lived token from YouTube's homepage
2. YOUTUBE_COOKIES - Full cookie string from your browser

These credentials allow YTDown to bypass bot detection on serverless platforms like Vercel.
"""

import os
import re
import urllib.request

def fetch_visitor_data():
    """Fetch and display the current VISITOR_DATA from YouTube."""
    print("=" * 70)
    print("Fetching VISITOR_DATA from YouTube...")
    print("=" * 70)

    try:
        req = urllib.request.Request(
            "https://www.youtube.com/",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Try both patterns
        patterns = [
            r'"VISITOR_DATA"\s*:\s*"([^"]+)"',
            r'"visitorData"\s*:\s*"([^"]+)"',
        ]

        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                visitor_data = m.group(1)
                print(f"\n[OK] Found VISITOR_DATA:\n{visitor_data}\n")
                print("[!] Note: VISITOR_DATA expires after a few hours. For production,")
                print("    consider using YOUTUBE_COOKIES which lasts longer.\n")
                return visitor_data

        print("\n[FAIL] Could not find VISITOR_DATA in the response.")
        print("   This may be due to YouTube serving a different page format.")
        print("   Try using YOUTUBE_COOKIES instead.\n")
        return None

    except Exception as e:
        print(f"\n[FAIL] Error fetching VISITOR_DATA: {e}\n")
        return None


def print_cookie_instructions():
    """Print instructions for getting YOUTUBE_COOKIES."""
    print("=" * 70)
    print("How to get YOUTUBE_COOKIES:")
    print("=" * 70)
    print("""
1. Open Chrome/Firefox and log into your YouTube account
2. Open Developer Tools (F12 or Right-click -> Inspect)
3. Go to the 'Application' tab (Chrome) or 'Storage' tab (Firefox)
4. On the left, select 'Cookies' -> 'https://www.youtube.com'
5. Select ALL cookie rows (click first, Shift+click last)
6. Right-click -> Copy -> Copy value (Chrome) or Copy string (Firefox)
7. Paste the entire string here:

> Example format:
SID=...; HSID=...; SSID=...; APISID=...; SAPISID=...; __Secure-1PSID=...; ...

8. Set this as the YOUTUBE_COOKIES environment variable on Vercel:

   Vercel Dashboard -> Your Project -> Settings -> Environment Variables
   Add: YOUTUBE_COOKIES = <paste your cookie string here>
   Select all environments (Production, Preview, Development)

9. Redeploy your project.

Note: Cookies last longer than VISITOR_DATA (typically months vs hours).
      Keep your cookies secure and never commit them to git.
""")


if __name__ == "__main__":
    print("""
--------------------------------------------------------
 YTDown Auth Credential Helper for Vercel
--------------------------------------------------------
""")

    fetch_visitor_data()
    print()
    print_cookie_instructions()

    print("=" * 70)
    print("Quick Setup (Recommended):")
    print("=" * 70)
    print("""
1. Get YOUTUBE_COOKIES as described above
2. In Vercel Dashboard, set environment variable:
   Key: YOUTUBE_COOKIES
   Value: <your cookie string>
3. Redeploy

Optional: Also set VISITOR_DATA if you want a fallback (auto-fetched locally).
""")
