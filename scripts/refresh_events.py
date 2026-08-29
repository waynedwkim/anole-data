#!/usr/bin/env python3
"""Refresh events.json: prune past events, pull fresh ones from sources
that expose structured data (The Events Calendar REST API).

Merge strategy: existing future events are kept (so hand-added and emailed
submissions survive); scraped events overlay by id. Stdlib only.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS_PATH = ROOT / "events.json"
ROSTER_PATH = ROOT / "series_roster.json"
HEALTH_PATH = ROOT / "health.json"

# A series is "running dry" once its last known date is this close. That is
# about how long it takes to find a replacement date, email an organizer, and
# wait for a reply.
DRY_HORIZON_DAYS = 60

# Sources with a working The Events Calendar REST API.
# Repticon stays manual: it is Cloudflare-gated on every route we know
# (wp-json, ?ical=1, plain HTML) as of 2026-08-29.
TRIBE_SOURCES = [
    {
        "seriesId": "cold-blooded-expos",
        "base": "https://coldbloodedexpos.com",
        "api": "https://coldbloodedexpos.com/wp-json/tribe/events/v1/events?per_page=50&start_date={start}",
    },
]

# Modern Events Calendar sites: the REST list carries no dates, so each event's
# ICS export is fetched for the real start/end. Diamondback runs the Maryland
# shows plus the Virginia and Pennsylvania ones we used to miss entirely.
MEC_SOURCES = [
    {
        "seriesId": "md-reptile-farm",
        "base": "https://mdreptilefarm.com",
        "list": "https://mdreptilefarm.com/wp-json/wp/v2/mec-events?per_page=100",
        "ical": "https://mdreptilefarm.com/?method=ical&id={id}",
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


USER_AGENT = "scalespot-data/1.0 (+https://github.com/waynedwkim/scalespot-data)"


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def unescape_title(value):
    """WordPress returns titles with HTML entities (&#8211; and friends)."""
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def parse_vevent(ics):
    """Reads the VEVENT block only — VTIMEZONE carries DTSTART lines too."""
    text = ics.replace("\r\n ", "").replace("\r\n\t", "")
    block = re.search(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S)
    if not block:
        return None
    body = block.group(1)

    def field(name):
        match = re.search(rf"^{name}[^:\r\n]*:(.*)$", body, re.M)
        return match.group(1).strip() if match else None

    return {
        "start": field("DTSTART"),
        "end": field("DTEND"),
        "location": field("LOCATION"),
    }


STREET_SUFFIXES = (
    "street", "st", "road", "rd", "avenue", "ave", "boulevard", "blvd",
    "drive", "dr", "lane", "ln", "pike", "way", "place", "pl", "highway",
    "hwy", "route", "rt", "circle", "cir", "court", "ct", "parkway", "pkwy",
)


def parse_location(value):
    """'890 West Main Street Berryville, VA 22611' -> ('Berryville', 'VA').

    Organizer addresses are inconsistent: some separate the city with a comma,
    others run the street straight into it.
    """
    if not value:
        return None, None
    cleaned = re.sub(r"\s+", " ", value.replace("\\,", ",")).strip()
    match = re.search(r"(.+?),?\s*\b([A-Za-z]{2})\b[,\s]*\d{0,5}\s*$", cleaned)
    if not match:
        return None, None
    state = match.group(2).upper()
    head = match.group(1).strip().rstrip(",")

    if "," in head:
        city = head.rsplit(",", 1)[-1]
    else:
        words = head.split()
        cut = 0
        for index, word in enumerate(words):
            if word.lower().strip(".") in STREET_SUFFIXES:
                cut = index + 1
        city = " ".join(words[cut:]) if cut else " ".join(words[-1:])

    city = re.sub(r"^\d+\s*", "", city).strip(" ,.")
    if not city or not re.search(r"[A-Za-z]", city):
        return None, state
    return city.title(), state


def scrape_mec(source, today):
    posts = fetch_json(source["list"])
    events = []
    for post in posts:
        title = unescape_title((post.get("title") or {}).get("rendered"))
        if not title:
            continue
        try:
            parsed = parse_vevent(fetch_text(source["ical"].format(id=post["id"])))
        except Exception:  # noqa: BLE001 — one dead event must not kill the run
            continue
        if not parsed or not parsed.get("start"):
            continue
        start = f"{parsed['start'][0:4]}-{parsed['start'][4:6]}-{parsed['start'][6:8]}"
        if start < today.isoformat():
            continue
        end = None
        if parsed.get("end"):
            raw_end = parsed["end"]
            end = f"{raw_end[0:4]}-{raw_end[4:6]}-{raw_end[6:8]}"
            if end == start:
                end = None
        city, state = parse_location(parsed.get("location"))
        if not state:
            continue
        events.append({
            "id": f"{source['seriesId']}-{slugify(city or title)}-{start}",
            "seriesId": source["seriesId"],
            "title": title,
            "city": city,
            "state": state,
            "venue": None,
            "startDate": start,
            "endDate": end,
            "url": post.get("link") or source["base"],
            "source": source["list"],
            "checkedAt": today.isoformat(),
        })
    return events


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


def write_health(events, today):
    """The refresh only ever prunes, so a neglected series doesn't break —
    it silently empties. Nobody notices a calendar that got smaller. This
    writes down what ran out so the workflow can say so out loud.
    """
    roster = json.loads(ROSTER_PATH.read_text()) if ROSTER_PATH.exists() else []
    horizon = (today + timedelta(days=DRY_HORIZON_DAYS)).isoformat()

    last_date = {}
    counts = {}
    for event in events:
        series = event.get("seriesId")
        if not series:
            continue
        counts[series] = counts.get(series, 0) + 1
        end = event.get("endDate") or event["startDate"]
        if end > last_date.get(series, ""):
            last_date[series] = end

    empty, expiring = [], []
    for entry in roster:
        series = entry["id"]
        record = {
            "id": series,
            "name": entry.get("name") or series,
            "website": entry.get("website"),
            "upcoming": counts.get(series, 0),
            "lastDate": last_date.get(series),
        }
        if record["upcoming"] == 0:
            empty.append(record)
        elif record["lastDate"] and record["lastDate"] < horizon:
            expiring.append(record)

    states = sorted({e["state"] for e in events if e.get("state")})
    health = {
        "checkedAt": today.isoformat(),
        "totalEvents": len(events),
        "states": len(states),
        "seriesTracked": len(roster),
        "seriesWithEvents": len([r for r in roster if counts.get(r["id"])]),
        "empty": sorted(empty, key=lambda r: r["name"]),
        "expiring": sorted(expiring, key=lambda r: r["lastDate"]),
    }
    HEALTH_PATH.write_text(json.dumps(health, indent=2, ensure_ascii=False) + "\n")

    print(f"health: {len(events)} events across {len(states)} states; "
          f"{len(empty)} series empty, {len(expiring)} running dry within {DRY_HORIZON_DAYS}d")
    for record in empty:
        print(f"  EMPTY    {record['name']}")
    for record in expiring:
        print(f"  DRY BY   {record['lastDate']}  {record['name']}")
    return health


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
    for source in MEC_SOURCES:
        try:
            scraped.extend(scrape_mec(source, today))
        except Exception as error:  # noqa: BLE001
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

    # Organizers overlap: the Diamondback feed also carries the All-Maryland
    # show we track as its own series. Collapse the same show on the same day
    # to one entry, keeping whichever id the file already had.
    previous_ids = {e["id"] for e in existing}

    def natural_key(event):
        title = re.sub(r"[^a-z0-9]+", "", (event.get("title") or "").lower())
        return (event["startDate"], event.get("state"), title)

    canonical = {}
    for event in merged.values():
        key = natural_key(event)
        incumbent = canonical.get(key)
        if incumbent is None:
            canonical[key] = event
            continue
        keep_incumbent = (incumbent["id"] in previous_ids) or (
            event["id"] not in previous_ids and incumbent["id"] < event["id"]
        )
        canonical[key] = incumbent if keep_incumbent else event
    deduped = len(merged) - len(canonical)

    result = sorted(canonical.values(), key=lambda e: (e["startDate"], e["id"]))
    EVENTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    write_health(result, today)

    print(f"pruned={pruned} scraped={len(scraped)} added={added} updated={updated} "
          f"deduped={deduped} total={len(result)}")
    if failures:
        print("source failures (non-fatal):", "; ".join(failures), file=sys.stderr)


if __name__ == "__main__":
    main()
