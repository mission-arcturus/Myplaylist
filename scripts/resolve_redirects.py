#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
import requests

PLAYLIST = Path("playlist.m3u")
TARGET_HOST = "arcturus.byethost14.com"
TARGET_PATH = "/redirect.php"
TIMEOUT = 30

def parse_pipe_options(text):
    headers = {}
    # M3U pipe options commonly look like:
    # |User-Agent=...&Cookie=...&referer=...
    for item in text.split("&"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
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

def is_target_url(url):
    try:
        parts = urlsplit(url)
        return parts.hostname == TARGET_HOST and parts.path == TARGET_PATH
    except Exception:
        return False

def resolve_redirect(url, headers):
    try:
        # GET is intentional: some redirect endpoints do not implement HEAD.
        response = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            stream=True,
            timeout=TIMEOUT,
        )
        final_url = response.url
        history = list(response.history)
        status = response.status_code
        response.close()

        # A redirect chain is useful even if the final media host rejects the
        # lightweight request (e.g. returns 403). Do not require final 2xx.
        if history and final_url != url:
            print(f"REDIRECT ({len(history)} hop(s), final HTTP {status}): {url} -> {final_url}")
            return final_url

        print(f"NOT RESOLVED (HTTP {status}, no HTTP redirect): {url}")
    except requests.RequestException as exc:
        print(f"REQUEST FAILED: {url} :: {exc}")
    return url

def main():
    if not PLAYLIST.exists():
        sys.exit("ERROR: playlist.m3u is missing.")

    original = PLAYLIST.read_text(encoding="utf-8-sig")
    lines = original.splitlines(keepends=True)
    pending_headers = {}
    updated_count = 0
    found_count = 0

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.lower().startswith("#extvlcopt:"):
            directive = stripped.split(":", 1)[1]
            if "=" in directive:
                key, value = directive.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
                if key == "http-user-agent":
                    pending_headers["User-Agent"] = value
                elif key == "http-cookie":
                    pending_headers["Cookie"] = value
                elif key == "http-referrer":
                    pending_headers["Referer"] = value
                elif key == "http-origin":
                    pending_headers["Origin"] = value
            continue

        if not stripped or stripped.startswith("#"):
            continue

        url, sep, options = stripped.partition("|")
        if not is_target_url(url):
            pending_headers = {}
            continue

        found_count += 1
        headers = dict(pending_headers)
        if sep:
            headers.update(parse_pipe_options(options))

        final_url = resolve_redirect(url, headers)
        if final_url != url:
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            # Preserve any player-specific pipe options after the URL.
            suffix = ("|" + options) if sep else ""
            lines[index] = final_url + suffix + newline
            updated_count += 1

        pending_headers = {}

    result = "".join(lines)
    if result != original:
        PLAYLIST.write_text(result, encoding="utf-8")
    print(f"SUMMARY: found={found_count}, updated={updated_count}")
    if found_count == 0:
        print("No matching redirect.php URLs were found.")
    if found_count and updated_count == 0:
        print("No HTTP Location redirect was exposed to the GitHub runner.")
        print("The endpoint may use JavaScript/HTML/JSON redirection or block GitHub Actions.")

if __name__ == "__main__":
    main()
