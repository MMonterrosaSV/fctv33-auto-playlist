#!/usr/bin/env python3
"""
FCTV33 Auto Playlist Generator
- Fetches live football matches via the site's real API (protobuf)
- Builds correct match page URLs
- Resolves them through https://fctv33-stream-resolver.onrender.com
- Outputs playlist.m3u with match names (not league names)
- After the list is ready, matches names against movitv.pro and steals tvg-logo when possible
"""
import re
import time
import requests
from datetime import datetime, timezone
RESOLVER = "https://fctv33-stream-resolver.onrender.com"
API_HOST = "https://apis-data-defra10.tcdru136ovur.ru"
SITE = "https://www.fctv33hd.icu"
MOVITV_PLAYLIST = "https://movitv.pro/"
# Only keep these competitions
ALLOWED_KEYWORDS = [
    "spanish-la-liga",
    "english-premier-league",
    "barcelona",
    "real-madrid",
    "italian-serie-a",
    "ukrainian-first-league",
    
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
        field = tag >> 3
        wire = tag & 7
        if wire != 2:
            if wire == 0:
                _, offset = read_varint(payload, offset)
            continue
        length, offset = read_varint(payload, offset)
        chunk = payload[offset : offset + length]
        offset += length
        if field == 1:
            raw_matches.append(chunk)
    results = []
    for mbuf in raw_matches:
        f = parse_fields(mbuf)
        match_id = f.get(1, [(None, None)])[0][1]
        if not match_id:
            continue
        # Title (the actual match name)
        title = None
        for _, v in f.get(30, []):
            if b" vs " in v:
                s = v.decode("utf-8", errors="ignore")
                s = re.sub(r"^[\x00-\x1f]+", "", s)
                if s and not s[0].isalpha():
                    s = s[1:]
                title = s.strip()
                break
        # Timestamp → MM-YYYY
        ts = f.get(3, [(None, None)])[0][1]
        month_year = "01-2026"
        if ts:
            try:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                month_year = f"{dt.month:02d}-{dt.year}"
            except Exception:
                pass
        # Competition slug + match slug (nested field 150)
        comp_slug = match_slug = None
        for _, v in f.get(150, []):
            inner = parse_fields(v)
            for _, iv in inner.get(20, []):
                if isinstance(iv, bytes):
                    match_slug = iv.decode("utf-8", errors="ignore")
            for _, iv in inner.get(21, []):
                if isinstance(iv, bytes):
                    comp_slug = iv.decode("utf-8", errors="ignore")
        if not (match_id and match_slug and comp_slug):
            continue
        url = (
            f"{SITE}/football/{comp_slug}-match-{match_id}/"
            f"{match_slug}-{month_year}.html"
        )
        results.append({
            "id": match_id,
            "title": title or match_slug,
            "url": url,
            "comp_slug": comp_slug,
        })
    return results
def is_allowed(match: dict) -> bool:
    text = f"{match['url']} {match.get('comp_slug', '')}".lower()
    return any(k in text for k in ALLOWED_KEYWORDS)
# ─────────────────────────── Resolve via your instance ───────────────────────────
def resolve_match(match_url: str) -> list[dict]:
    try:
        r = requests.get(
            f"{RESOLVER}/api/resolve-link",
            params={"url": match_url},
            timeout=90,
        )
        print(f"  Resolver status: {r.status_code}")
        if r.status_code != 200:
            return []
        data = r.json()
        # Handle both single-stream and multi-stream responses
        if "streams" in data and isinstance(data["streams"], list):
            return data["streams"]
        if "playableUrl" in data:
            return [data]
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []
# ─────────────────────────── movitv.pro logo matching ───────────────────────────
def normalize_match_name(name: str) -> str:
    """Lowercase, strip punctuation, drop trailing (2)/(3), expand a few common abbreviations."""
    name = name.lower()
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\b(vs|v|fc|cf|sc|ac|the)\b", " ", name)
    name = re.sub(r"\bpsg\b", "paris germain", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name
def extract_teams(name: str) -> set:
    """Split a match name into individual team tokens (len > 2)."""
    parts = re.split(r"\s+", normalize_match_name(name))
    return {p for p in parts if len(p) > 2}
def fetch_movitv_logos(session: requests.Session) -> list:
    """
    Download https://movitv.pro/ and return [{"name": "...", "logo": "https://..."}, ...]
    Only keeps entries that look like match events (contain -, vs, v, or @).
    """
    try:
        r = session.get(MOVITV_PLAYLIST, timeout=25)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        print(f"  Could not fetch movitv playlist: {e}")
        return []
    logos = []
    pattern = re.compile(
        r'#EXTINF:[^\n]*?tvg-logo="([^"]+)"[^\n]*,\s*(.+)',
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        logo_url = m.group(1).strip()
        event_name = m.group(2).strip()
        if not logo_url or not event_name:
            continue
        if any(sep in event_name for sep in ("-", " vs ", " v ", "@")):
            logos.append({"name": event_name, "logo": logo_url})
    print(f"  movitv events with logos: {len(logos)}")
    return logos
def find_logo(match_name: str, movitv_entries: list):
    """Return matching logo URL if both team names overlap, else None."""
    our_teams = extract_teams(match_name)
    if len(our_teams) < 2:
        return None
    best_logo = None
    best_score = 0
    for entry in movitv_entries:
        their_teams = extract_teams(entry["name"])
        if not their_teams:
            continue
        overlap = len(our_teams & their_teams)
        if overlap > best_score:
            best_score = overlap
            best_logo = entry["logo"]
            if best_score >= 2:
                break
    return best_logo if best_score >= 2 else None
# ─────────────────────────── Main ───────────────────────────
def main():
    print("=" * 70)
    print("FCTV33 Auto Playlist Generator")
    print("=" * 70)
    session = requests.Session()
    session.headers.update(HEADERS)
    print("\n1. Fetching live matches from API…")
    data = get_live_payload(session)
    all_matches = extract_matches(data)
    print(f"   Total matches found: {len(all_matches)}")
    # Filter
    matches = [m for m in all_matches if is_allowed(m)]
    print(f"   After keyword filter: {len(matches)}")
    if not matches:
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n# No matching live matches found\n")
        print("No allowed matches → empty playlist written")
        return
    print("\n2. Resolving streams…")
    streams = []
    for i, m in enumerate(matches, 1):
        print(f"\n[{i}/{len(matches)}] {m['title']}")
        print(f"  URL: {m['url']}")
        for data in resolve_match(m["url"]):
            # Always prefer the clean match name we extracted
            name = m["title"] or data.get("name") or "Unknown"
            playable = data.get("playableUrl")
            if playable:
                streams.append({"name": name, "url": playable})
                print(f"  → {name}")
        time.sleep(3)  # be nice to the free Render instance
    # ── 3. After list is ready: steal logos from movitv.pro ──────────────
    print("\n3. Matching logos from movitv.pro…")
    movitv_entries = fetch_movitv_logos(session)
    logo_hits = 0
    for s in streams:
        logo = find_logo(s["name"], movitv_entries)
        if logo:
            s["logo"] = logo
            logo_hits += 1
            print(f"  ✓ {s['name']}  →  {logo}")
        else:
            print(f"  ✗ {s['name']}  (no match – left as is)")
    # Write playlist
    lines = [
        "#EXTM3U",
        f"# Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"# Matches: {len(matches)} | Streams: {len(streams)} | Logos: {logo_hits}",
    ]
    for s in streams:
        if s.get("logo"):
            lines.append(
                f'#EXTINF:-1 tvg-logo="{s["logo"]}" group-title="FCTV33 LIVE EVENTS",{s["name"]}'
            )
        else:
            lines.append(f'#EXTINF:-1 group-title="FCTV33 LIVE EVENTS",{s["name"]}')
        lines.append(s["url"])
    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n" + "=" * 70)
    print(f"Done → {len(streams)} streams ({logo_hits} with logos) written to playlist.m3u")
    print("=" * 70)
if __name__ == "__main__":
    main()
