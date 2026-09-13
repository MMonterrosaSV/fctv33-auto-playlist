#!/usr/bin/env python3
import os
import time
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

RESOLVER = "https://fctv33-stream-resolver.onrender.com"  # ← change if your Render URL is different
FOOTBALL_URL = "https://www.fctv33hd.icu/football.html"

def get_live_match_urls() -> list[str]:
    """Open the football page with a real browser and extract live match links."""
    urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        print("Loading football page...")
        page.goto(FOOTBALL_URL, wait_until="networkidle", timeout=60000)
        
        # Wait a bit extra for live matches to appear
        page.wait_for_timeout(8000)

        # Extract all links that look like match pages
        links = page.eval_on_selector_all(
            "a[href*='/football/'][href*='-match-']",
            "elements => elements.map(el => el.href)"
        )
        
        # Keep only unique live-looking match pages
        seen = set()
        for link in links:
            if link not in seen and "match-" in link and link.endswith(".html"):
                seen.add(link)
                urls.append(link)

        browser.close()
    
    print(f"Found {len(urls)} match links")
    return urls

def resolve_match(match_url: str) -> dict | None:
    try:
        r = requests.get(
            f"{RESOLVER}/api/resolve-link",
            params={"url": match_url},
            timeout=90
        )
        if r.status_code != 200:
            print(f"  Resolve failed ({r.status_code}): {match_url}")
            return None
        data = r.json()
        if "playableUrl" in data:
            return data
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def main():
    print("Starting automatic playlist generation...")
    
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
        time.sleep(4)  # be gentle with free Render

    # Write the playlist
    lines = ["#EXTM3U"]
    lines.append(f"# Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"# Source: {FOOTBALL_URL}")
    
    for s in streams:
        lines.append(f'#EXTINF:-1 group-title="FCTV33 Live",{s["name"]}')
        lines.append(s["url"])

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nDone! playlist.m3u created with {len(streams)} live streams")

if __name__ == "__main__":
    main()
