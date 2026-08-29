"""Read Expo Idaho's own reptile-show dates.

The venue refuses the maintainer's network but answers a US GitHub runner,
which is why Idaho sits in the feed as "blocked, not empty". Search results
carry titles but no dates, so this follows each event link and reads the date
off the event page itself — the venue's own booking record.
"""
import html
import re
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def visible(raw):
    raw = re.sub(r"<(script|style).*?</\1>", " ", raw, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


links = set()
for page in range(1, 6):
    url = "https://expoidaho.com/?s=reptile" if page == 1 else f"https://expoidaho.com/page/{page}/?s=reptile"
    try:
        raw = fetch(url)
    except Exception as error:  # noqa: BLE001
        print(f"search page {page} failed: {error}")
        continue
    links |= set(re.findall(r'https://expoidaho\.com/event/[^"\'\s>]+', raw))

print(f"{len(links)} event links found\n")

for link in sorted(links):
    try:
        body = visible(fetch(link))
    except Exception as error:  # noqa: BLE001
        print(f"{link}\n  failed: {error}")
        continue
    # Dates appear as "October 17, 2026" / "Oct 17 2026" style strings.
    dates = re.findall(
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2}(?:\s*[-–]\s*\d{1,2})?,?\s+20\d{2}", body)
    slug_date = re.search(r"/(20\d{2}-\d{2}-\d{2})/", link)
    print(link)
    print(f"  slug date : {slug_date.group(1) if slug_date else '-'}")
    print(f"  page dates: {sorted(set(dates))[:6] or '-'}")
