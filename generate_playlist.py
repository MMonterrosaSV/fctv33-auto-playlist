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
    "mls",
]

def is_allowed_match(url: str) -> bool:
    url_lower = url.lower()
    return any(k in url_lower for k in ALLOWED_KEYWORDS)

def get_live_match_urls() -> list[str]:
    urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        )

        # Hide webdriver flag
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        print("Loading football page with stealth settings...")
        try:
            page.goto(FOOTBALL_URL, wait_until="networkidle", timeout=90000)
        except Exception as e:
            print(f"goto error: {e}")
            page.goto(FOOTBALL_URL, timeout=90000)

        page.wait_for_timeout(12000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(4000)

        title = page.title()
        print(f"Page title: '{title}'")

        # Dump a small part of the HTML so we can see what we got
        html = page.content()
        print(f"HTML length: {len(html)}")
        print("First 500 chars of HTML:")
        print(html[:500])
        print("...")

        # Get all links
        all_hrefs = page.eval_on_selector_all(
            "a",
            "els => els.map(el => el.href)"
        )
        print(f"Total <a> tags: {len(all_hrefs)}")

        football_links = [h for h in all_hrefs if h and "/football/" in h.lower()]
        print(f"Football links: {len(football_links)}")
        for link in football_links[:15]:
            print(f"  {link}")

        seen = set()
        for link in football_links:
            if link not in seen and "match-" in link.lower() and link.endswith(".html"):
                seen.add(link)
                if is_allowed_match(link):
                    urls.append(link)
                    print(f"  ✓ {link}")
                else:
                    print(f"  ✗ {link}")

        browser.close()

    print(f"\nAllowed matches found: {len(urls)}")
    return urls

def resolve_match(match_url: str) -> list[dict]:
    try:
        r = requests.get(f"{RESOLVER}/api/resolve-link", params={"url": match_url}, timeout=90)
        print(f"  Resolver status: {r.status_code}")
        if r.status_code != 200:
            return []
        data = r.json()
        if "streams" in data and isinstance(data["streams"], list):
            return data["streams"]
        if "playableUrl" in data:
            return [data]
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

def main():
    print("=" * 60)
    match_urls = get_live_match_urls()

    if not match_urls:
        with open("playlist.m3u", "w") as f:
            f.write("#EXTM3U\n# No matching live matches found\n")
        print("No matches → empty playlist written")
        return

    streams = []
    for i, url in enumerate(match_urls, 1):
        print(f"\n[{i}/{len(match_urls)}] {url}")
        for data in resolve_match(url):
            name = data.get("name", "Unknown")
            if data.get("playableUrl"):
                streams.append({"name": name, "url": data["playableUrl"]})
                print(f"  → {name}")
        time.sleep(4)

    lines = ["#EXTM3U", f"# {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]
    for s in streams:
        lines.append(f'#EXTINF:-1 group-title="FCTV33 Selected",{s["name"]}')
        lines.append(s["url"])

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nDone → {len(streams)} streams")

if __name__ == "__main__":
    main()
