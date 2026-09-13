#!/usr/bin/env python3
import os
import time
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

RESOLVER = "https://fctv33-stream-resolver.onrender.com"  # ← change if needed
FOOTBALL_URL = "https://www.fctv33hd.icu/football.html"

# Only these leagues are allowed
ALLOWED_KEYWORDS = [
    "united-states-major-league-soccer",   # MLS
    "major-league-soccer",
    "spanish-la-liga",                     # La Liga
    "la-liga",
    "english-premier-league",              # Premier League
    "premier-league",
]

def is_allowed_match(url: str) -> bool:
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in ALLOWED_KEYWORDS)

def get_live_match_urls() -> list[str]:
    """Open the football page and extract only the allowed league match links."""
    urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        print("Loading football page...")
        page.goto(FOOTBALL_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(8000)

        links = page.eval_on_selector_all(
            "a[href*='/football/'][href*='-match-']",
            "elements => elements.map(el => el.href)"
        )

        seen = set()
        for link in links:
            if (link not in seen 
                and "match-" in link 
                and link.endswith(".html")
                and is_allowed_match(link)):
                seen.add(link)
                urls.append(link)

        browser.close()
    
    print(f"Found {len(urls)} allowed match links (MLS + La Liga + Premier League)")
    return urls

def resolve_match(match_url: str) -> dict | None:
    try:
        r = requests.get(
            f"{RESOLVER}/api/resolve-link",
            params={"url": match_url},
            timeout=90
        )
        if r.status_code != 200:
            print(f"  Resolve failed ({r.status_code})")
            return None
        data = r.json()
        if "playableUrl" in data:
            return data
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def main():
    print("Starting automatic playlist generation (MLS + La Liga + Premier League only)...")
    
    match_urls = get_live_match_urls()
    
    streams = []
    for i, url in enumerate(match_urls, 1):
        print(f"[{i}/{len(match_urls)}] Resolving: {url}")
        data = resolve_match(url)
        if data:
            name = data.get("name", "Unknown Match")
            streams.append({
                "name": name,
                "url": data["playableUrl"]
            })
            print(f"  → {name}")
        time.sleep(4)

    # Write the playlist
    lines = ["#EXTM3U"]
    lines.append(f"# Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("# Leagues: MLS + La Liga + Premier League")
    
    for s in streams:
        lines.append(f'#EXTINF:-1 group-title="FCTV33 Selected",{s["name"]}')
        lines.append(s["url"])

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nDone! playlist.m3u created with {len(streams)} streams")

if __name__ == "__main__":
    main()
