#!/usr/bin/env python3
"""Refresh events.json: prune past events, pull fresh ones from sources
that expose structured data (The Events Calendar REST API).

Merge strategy: existing future events are kept (so hand-added and emailed
submissions survive); scraped events overlay by id. Stdlib only.
"""
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS_PATH = ROOT / "events.json"

# Sources with a working The Events Calendar REST API.
# Repticon is Cloudflare-gated and mdreptilefarm has no REST route — those
# stay manual/email-curated.
TRIBE_SOURCES = [
    {
        "seriesId": "cold-blooded-expos",
        "base": "https://coldbloodedexpos.com",
        "api": "https://coldbloodedexpos.com/wp-json/tribe/events/v1/events?per_page=50&start_date={start}",
    },
]

STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def normalize_state(value):
    if not value:
        return None
    value = value.strip()
    if len(value) == 2:
        return value.upper()
    return STATE_NAMES.get(value.lower())


def slugify(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def tidy_venue(value):
    """SHOUTING venue names from source CMSes read badly in the app."""
    if not value:
        return None
    letters = [c for c in value if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return " ".join(w if w in {"@", "&"} else w.capitalize() for w in value.split())
    return value


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "scalespot-data/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def scrape_tribe(source, today):
    url = source["api"].format(start=today.isoformat())
    payload = fetch_json(url)
    events = []
    for item in payload.get("events", []):
        start = (item.get("start_date") or "")[:10]
        end = (item.get("end_date") or "")[:10]
        venue = item.get("venue") or {}
        if isinstance(venue, list):
            venue = venue[0] if venue else {}
        state = normalize_state(venue.get("stateprovince") or venue.get("state"))
        title = re.sub(r"\s+", " ", (item.get("title") or "").strip())
        if not (start and title and state):
            continue
        events.append({
            "id": f"{source['seriesId']}-{slugify(venue.get('city') or title)}-{start}",
            "seriesId": source["seriesId"],
            "title": title,
            "city": venue.get("city"),
            "state": state,
            "venue": tidy_venue(venue.get("venue")),
            "startDate": start,
            "endDate": end if end and end != start else None,
            "url": item.get("url") or source["base"],
            "source": url,
            "checkedAt": today.isoformat(),
        })
    return events


def main():
    today = date.today()
    cutoff = (today - timedelta(days=1)).isoformat()

    existing = json.loads(EVENTS_PATH.read_text())
    kept = [e for e in existing if (e.get("endDate") or e["startDate"]) >= cutoff]
    pruned = len(existing) - len(kept)

    scraped, failures = [], []
    for source in TRIBE_SOURCES:
        try:
            scraped.extend(scrape_tribe(source, today))
        except Exception as error:  # noqa: BLE001 — a dead source must not kill the run
            failures.append(f"{source['seriesId']}: {error}")

    merged = {e["id"]: e for e in kept}
    added = updated = 0

    def substance(event):
        # checkedAt moves on every run; it shouldn't count as a change.
        return {k: v for k, v in event.items() if k != "checkedAt"}

    for event in scraped:
        previous = merged.get(event["id"])
        if previous is None:
            added += 1
        elif substance(previous) != substance(event):
            updated += 1
        merged[event["id"]] = event

    result = sorted(merged.values(), key=lambda e: (e["startDate"], e["id"]))
    EVENTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    print(f"pruned={pruned} scraped={len(scraped)} added={added} updated={updated} total={len(result)}")
    if failures:
        print("source failures (non-fatal):", "; ".join(failures), file=sys.stderr)


if __name__ == "__main__":
    main()
