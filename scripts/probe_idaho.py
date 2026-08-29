"""Pull Expo Idaho's own reptile-show listings.

The venue refuses requests from the maintainer's network but answers a US
GitHub runner, which is why Idaho sits in the feed as "blocked, not empty".
"""
import html
import re
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
URLS = [
    "https://expoidaho.com/events/",
    "https://expoidaho.com/?s=reptile",
    "https://expoidaho.com/events/list/",
]


def text_of(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", "replace")
    raw = re.sub(r"<(script|style).*?</\1>", " ", raw, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


for url in URLS:
    print(f"===== {url}")
    try:
        body = text_of(url)
    except Exception as error:  # noqa: BLE001
        print(f"  failed: {error}")
        continue
    hits = [m.group(0).strip() for m in re.finditer(r".{0,120}[Rr]eptile.{0,240}", body)]
    if not hits:
        print("  no reptile mentions")
    for hit in hits[:12]:
        print(f"  · {hit}")
        print("  ---")
