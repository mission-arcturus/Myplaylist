#!/usr/bin/env python3
"""
Resolve HTTP redirects for redirect.php URLs in playlist.m3u.
Only replace a URL when an actual HTTP redirect reaches a different URL.
M3U metadata, ordering, and pipe-delimited player options are preserved.
"""
from pathlib import Path
import re
import sys
import requests

PLAYLIST = Path("playlist.m3u")
TARGET = "arcturus.byethost14.com/redirect.php"
TIMEOUT = 25

def parse_options(option_text):
    headers = {}
    # Supports the common M3U pipe syntax:
    # |User-Agent=...&Cookie=... and |referer=...
    parts = re.split(r"[&|]", option_text)
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in ("user-agent", "http-user-agent"):
            headers["User-Agent"] = value
        elif key in ("cookie", "http-cookie"):
            headers["Cookie"] = value
        elif key in ("referer", "http-referrer"):
            headers["Referer"] = value
        elif key == "origin":
            headers["Origin"] = value
    return headers

def resolve(url, headers):
    try:
        response = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=TIMEOUT,
            stream=True,
        )
        final_url = response.url
        status = response.status_code
        response.close()

        # Do not replace with an error page or a URL that did not redirect.
        if 200 <= status < 400 and final_url != url:
            return final_url
        print(f"SKIP (no usable HTTP redirect, status {status}): {url}")
    except requests.RequestException as exc:
        print(f"SKIP (request failed): {url} :: {exc}")
    return url

def main():
    if not PLAYLIST.exists():
        print("ERROR: playlist.m3u was not found in the repository root.")
        sys.exit(1)

    original = PLAYLIST.read_text(encoding="utf-8-sig")
    lines = original.splitlines(keepends=True)
    changed = 0
    pending_headers = {}

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.lower().startswith("#extvlcopt:"):
            directive = stripped.split(":", 1)[1]
            if "=" in directive:
                key, value = directive.split("=", 1)
                key = key.strip().lower()
                if key in ("http-user-agent", "http-cookie", "http-referrer"):
                    pending_headers[key] = value.strip()
            continue

        if not stripped or stripped.startswith("#"):
            continue

        url_part, separator, player_options = stripped.partition("|")
        if TARGET not in url_part:
            pending_headers = {}
            continue

        headers = {}
        if "http-user-agent" in pending_headers:
            headers["User-Agent"] = pending_headers["http-user-agent"]
        if "http-cookie" in pending_headers:
            headers["Cookie"] = pending_headers["http-cookie"]
        if "http-referrer" in pending_headers:
            headers["Referer"] = pending_headers["http-referrer"]
        if separator:
            headers.update(parse_options(player_options))

        final_url = resolve(url_part, headers)
        if final_url != url_part:
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            suffix = f"|{player_options}" if separator else ""
            lines[index] = f"{final_url}{suffix}{newline}"
            changed += 1
            print(f"UPDATED: {url_part} -> {final_url}")

        pending_headers = {}

    updated = "".join(lines)
    if updated != original:
        PLAYLIST.write_text(updated, encoding="utf-8")
        print(f"Done. Updated {changed} redirect URL(s).")
    else:
        print("Done. No playlist changes were made.")

if __name__ == "__main__":
    main()
  
