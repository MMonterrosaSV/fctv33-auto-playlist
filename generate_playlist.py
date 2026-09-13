#!/usr/bin/env python3
import time
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

RESOLVER = "https://fctv33-stream-resolver.onrender.com"
FOOTBALL_URL = "https://www.fctv33hd.icu/football.html"

ALLOWED_KEYWORDS = [
    "USA: United States Major League Soccer",
    "united-states-major-league-soccer-match",
    "united-states-major-league-soccer",
    "major-league-soccer",
    "spanish-la-liga",
    "la-liga",
    "english-premier-league",
    "premier-league",
    "mls",           # extra safety
]

def is_allowed_match(url: str) -> bool:
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in ALLOWED_KEYWORDS)

def get_live_match_urls() -> list[str]:
    urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        print("Loading football page...")
        page.goto(FOOTBALL_URL, wait_until="domcontentloaded", timeout=90000)
        
        # Wait longer and try to scroll to trigger lazy loading
        page.wait_for_timeout(5000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(3000)

        # Method 1: Get every single <a> tag on the page
        all_hrefs = page.eval_on_selector_all(
            "a",
            "els => els.map(el => el.href).filter(h => h && h.includes('http'))"
        )
        print(f"Total <a> links found: {len(all_hrefs)}")

        # Method 2: Also try specific football patterns
        football_links = [h for h in all_hrefs if "/football/" in h.lower()]
        print(f"Links containing '/football/': {len(football_links)}")

        for link in football_links[:20]:
            print(f"  → {link}")

        # Filter for real match pages
        seen = set()
        for link in football_links:
            if (link not in seen
                and "match-" in link.lower()
                and link.endswith(".html")):
                seen.add(link)
                if is_allowed_match(link):
                    urls.append(link)
                    print(f"  ✓ ALLOWED: {link}")
                else:
                    print(f"  ✗ skipped: {link}")

        # Extra debug: print page title and some text
        title = page.title()
        print(f"\nPage title: {title}")
        
        browser.close()

    print(f"\nFinal allowed matches: {len(urls)}")
    return urls

def resolve_match(match_url: str) -> list[dict]:
    try:
        print(f"  Calling resolver...")
        r = requests.get(
            f"{RESOLVER}/api/resolve-link",
            params={"url": match_url},
            timeout=90
        )
        print(f"  Status: {r.status_code}")

        if r.status_code != 200:
            print(f"  Body: {r.text[:200]}")
            return []

        data = r.json()

        if "streams" in data and isinstance(data["streams"], list):
            print(f"  → {len(data['streams'])} streams returned")
            return data["streams"]

        if "playableUrl" in data:
            print("  → 1 stream (old format)")
            return [data]

        print(f"  Unexpected keys: {list(data.keys())}")
        return []
    except Exception as e:
        print(f"  Exception: {e}")
        return []

def main():
    print("=" * 60)
    print("DEBUG playlist generation")
    print("=" * 60)

    match_urls = get_live_match_urls()

    if not match_urls:
        print("\nNo allowed matches found.")
        with open("playlist.m3u", "w") as f:
            f.write("#EXTM3U\n# No matching live matches found at this time\n")
        return

    streams = []
    for i, url in enumerate(match_urls, 1):
        print(f"\n[{i}/{len(match_urls)}] {url}")
        resolved = resolve_match(url)
        for data in resolved:
            name = data.get("name", "Unknown")
            playable = data.get("playableUrl")
            if playable:
                streams.append({"name": name, "url": playable})
                print(f"  Added: {name}")
        time.sleep(4)

    lines = ["#EXTM3U"]
    lines.append(f"# Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"# Streams: {len(streams)}")

    for s in streams:
        lines.append(f'#EXTINF:-1 group-title="FCTV33 Selected",{s["name"]}')
        lines.append(s["url"])

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n✅ playlist.m3u created with {len(streams)} streams")

if __name__ == "__main__":
    main()
