#!/usr/bin/env python3
"""
FCTV33 Auto Playlist Generator
- Fetches live football matches via the site's real API (protobuf)
- Builds correct match page URLs
- Resolves them through https://fctv33-stream-resolver.onrender.com
- Outputs playlist.m3u
"""

import re
import time
import requests
from datetime import datetime, timezone

RESOLVER = "https://fctv33-stream-resolver.onrender.com"
API_HOST = "https://apis-data-defra10.tcdru136ovur.ru"
SITE = "https://www.fctv33hd.icu"

# Only keep these competitions
ALLOWED_KEYWORDS = [
    "united-states-major-league-soccer",
    "major-league-soccer",
    "spanish-la-liga",
    "la-liga",
    "english-premier-league",
    "premier-league",
    "mls",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Origin": SITE,
    "Referer": f"{SITE}/",
}


# ─────────────────────────── Protobuf helpers ───────────────────────────

def read_varint(buf: bytes, offset: int):
    value = 0
    shift = 0
    i = offset
    while i < len(buf):
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, i
        shift += 7
    return None, i


def parse_fields(buf: bytes) -> dict:
    fields = {}
    off = 0
    while off < len(buf):
        tag, off = read_varint(buf, off)
        if tag is None:
            break
        field = tag >> 3
        wire = tag & 7
        if wire == 0:
            val, off = read_varint(buf, off)
            fields.setdefault(field, []).append(("v", val))
        elif wire == 2:
            length, off = read_varint(buf, off)
            chunk = buf[off : off + length]
            off += length
            fields.setdefault(field, []).append(("b", chunk))
        else:
            break
    return fields


# ─────────────────────────── Fetch live matches ───────────────────────────

def get_live_payload(session: requests.Session) -> bytes:
    """Try recent signed endpoints until one works."""
    candidates = [
        f"{API_HOST}/sfverdab4bf2dcada5d245aec29071696df9d0c108c/api/match/live",
        f"{API_HOST}/sfverdab4bfebd09dfe16220cc5f83b7cd68ca28b60/api/match/live",
    ]
    params = {"sportType": "1", "language": "0", "stream": "true"}

    for base in candidates:
        try:
            r = session.get(base, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200 and len(r.content) > 5000:
                print(f"Using endpoint: {base}")
                return r.content
        except Exception as e:
            print(f"Endpoint failed: {e}")
    raise RuntimeError("Could not fetch live match list – signed path may have rotated")


def extract_matches(data: bytes) -> list[dict]:
    """Parse protobuf → list of {id, title, url}."""
    # Top-level field 10 contains the match list
    offset = 0
    payload = None
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        if tag is None:
            break
        field = tag >> 3
        wire = tag & 7
        if wire == 2:
            length, offset = read_varint(data, offset)
            if field == 10:
                payload = data[offset : offset + length]
                break
            offset += length
        elif wire == 0:
            _, offset = read_varint(data, offset)

    if not payload:
        raise RuntimeError("No match list found in response")

    # Each match is a length-delimited field 1
    raw_matches = []
    offset = 0
    while offset < len(payload):
        tag, offset = read_varint(payload, offset)
        if tag is None:
            break
