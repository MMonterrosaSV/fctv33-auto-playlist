#!/usr/bin/env python3
import time
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

RESOLVER = "https://fctv33-stream-resolver.onrender.com"
FOOTBALL_URL = "https://www.fctv33hd.icu/football.html"

ALLOWED_KEYWORDS = [
    "united-states-major-league-soccer",
    "major-league-soccer",
    "spanish-la-liga",
    "la-liga",
    "english-premier-league",
    "premier-league",
]

def is_allowed_match(url: str) -> bool:
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in ALLOWED_KEYWORDS)

def get_live_match_urls() -> list[str]:
    urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        print("Loading football page...")
        page.goto(FOOTBALL_URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(10000)  # wait longer

        # Get ALL football match links first
        all_links = page.eval_on_selector_all(
            "a[href*='/football/']",
            "elements => elements.map(el => el.href)"
        )
        print(f"Total football links found on page: {len(all_links)}")

        # Show some examples
        for link in all_links[:15]:
            print(f"  Example: {link}")

        seen = set()
        for link in all_links:
            if (link not in seen
                and "match-" in link
                and link.endswith(".html")):
                seen.add(link)

                if is_allowed_match(link):
                    urls.append(link)
                    print(f"  ✓ ALLOWED: {link}")
                else:
                    print(f"  ✗ skipped: {link}")

        browser.close()

    print(f"\nFinal allowed matches: {len(urls)}")
    return urls

def resolve_match(match_url: str) -> list[dict]:
    try:
        print(f"  Calling resolver for: {match_url}")
        r = requests.get(
            f"{RESOLVER}/api/resolve-link",
            params={"url": match_url},
            timeout=90
        )
        print(f"  Status: {r.status_code}")

        if r.status_code != 200:
            print(f"  Response: {r.text[:300]}")
            return []

        data = r.json()
        print(f"  Keys in response: {list(data.keys())}")

        if "streams" in data and isinstance(data["streams"], list):
            print(f"  Found {len(data['streams'])} streams")
            return data["streams"]

        if "playableUrl" in data:
            print("  Found single stream (old format)")
            return [data]

        print(f"  Unexpected response: {data}")
        return []
    except Exception as e:
        print(f"  Exception: {e}")
        return []

def main():
    print("=" * 60)
    print("Starting playlist generation with DEBUG logging")
    print("=" * 60)

    match_urls = get_live_match_urls()

    if not match_urls:
        print("\n⚠️  No matching league links were found.")
        print("The filter may be too strict or there are no live matches right now.")
        # Create empty playlist so the Action still succeeds
        with open("playlist.m3u", "w") as f:
            f.write("#EXTM3U\n# No matching live matches found\n")
        return

    streams = []
    for i, url in enumerate(match_urls, 1):
        print(f"\n[{i}/{len(match_urls)}] Processing: {url}")
        resolved = resolve_match(url)

        for data in resolved:
            name = data.get("name", "Unknown")
            playable = data.get("playableUrl")
            if playable:
                streams.append({"name": name, "url": playable})
                print(f"  → Added: {name}")

        time.sleep(4)

    # Write playlist
    lines = ["#EXTM3U"]
    lines.append(f"# Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"# Found {len(streams)} streams")

    for s in streams:
        lines.append(f'#EXTINF:-1 group-title="FCTV33 Selected",{s["name"]}')
        lines.append(s["url"])

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n✅ Finished. playlist.m3u has {len(streams)} streams")

if __name__ == "__main__":
    main()
