#!/usr/bin/env python3
"""Generate subscribable calendar feeds from events.json.

One feed per organizer series plus a combined feed. Organizers link these from
their own pages; keepers subscribe once and the dates keep arriving. This is the
half of the badge that keeps working after someone closes the browser tab.

Correctness notes that are easy to get wrong:

- For all-day events DTEND is EXCLUSIVE. A show running Sat-Sun must end on
  Monday's date or every calendar client renders it a day short.
- DTSTAMP is derived from the event's own checkedAt rather than "now", so a run
  that changes no data produces no diff. Otherwise every scheduled run would
  rewrite 36 files and the real changes would be invisible in the history.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "ics"
PRODID = "-//Anole//Verified US reptile expo calendar//EN"
# Same-origin base for the links embedded in each event.
SITE = "https://waynedwkim.github.io/anole-data"


def escape(value: str) -> str:
    """Escape a text value per RFC 5545 section 3.3.11."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Fold a content line to 75 octets, continuing with a leading space.

    Folding is measured in octets, not characters, so a multi-byte character
    must never be split across the boundary.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, start = [], 0
    limit = 75
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Back off until we land on a character boundary.
        while end > start and end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
        limit = 74  # continuation lines carry a leading space
    return "\r\n ".join(chunks)


def parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def location_of(event: dict) -> str:
    parts = [event.get("venue"), event.get("city"), event.get("state")]
    return ", ".join(p for p in parts if p)


def to_vevent(event: dict) -> list[str] | None:
    start = parse_day(event.get("startDate", ""))
    if start is None:
        return None
    end = parse_day(event.get("endDate") or "") or start
    if end < start:
        end = start

    checked = parse_day(event.get("checkedAt") or "") or start
    stamp = f"{checked:%Y%m%d}T000000Z"

    description = (
        f"Verified against the organizer's own schedule on {checked:%Y-%m-%d}. "
        "Dates can move; confirm with the organizer before travelling."
    )

    lines = [
        "BEGIN:VEVENT",
        f"UID:{event['id']}@anole.app",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
        # Exclusive end date: add one day so the last show day renders.
        f"DTEND;VALUE=DATE:{end + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{escape(event.get('title', 'Reptile expo'))}",
        "TRANSP:TRANSPARENT",
    ]
    location = location_of(event)
    if location:
        lines.append(f"LOCATION:{escape(location)}")
    url = event.get("url") or event.get("source")
    if url:
        lines.append(f"URL:{escape(url)}")
    lines.append(f"DESCRIPTION:{escape(description)}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(name: str, events: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
        "X-WR-TIMEZONE:UTC",
        f"X-WR-CALDESC:{escape(f'{name} — dates verified against the organizer.')}",
        # Ask clients not to hammer a static file more than hourly.
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for event in sorted(events, key=lambda e: (e.get("startDate", ""), e.get("id", ""))):
        block = to_vevent(event)
        if block:
            lines.extend(block)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def main() -> None:
    events = json.loads((ROOT / "events.json").read_text())
    roster = json.loads((ROOT / "series_roster.json").read_text())
    names = {s["id"]: s["name"] for s in roster}

    OUT_DIR.mkdir(exist_ok=True)
    # Drop feeds for series that no longer exist rather than leaving stale files
    # that organizers may still be linking.
    keep = set()

    # Seed from the roster, not from the events. A series whose next date is not
    # announced yet still has organizers linking its feed; emitting nothing would
    # turn their badge's calendar button into a 404. An empty VCALENDAR is valid
    # and simply shows no events.
    by_series: dict[str, list[dict]] = {s["id"]: [] for s in roster}
    for event in events:
        by_series.setdefault(event.get("seriesId", "unknown"), []).append(event)

    for series_id, series_events in sorted(by_series.items()):
        name = names.get(series_id, series_id)
        path = OUT_DIR / f"{series_id}.ics"
        path.write_text(build_calendar(name, series_events), newline="")
        keep.add(path.name)

    all_path = OUT_DIR / "all.ics"
    all_path.write_text(
        build_calendar("US reptile expos — verified", events), newline=""
    )
    keep.add(all_path.name)

    for stale in OUT_DIR.glob("*.ics"):
        if stale.name not in keep:
            stale.unlink()
            print(f"removed stale feed {stale.name}")

    print(f"wrote {len(keep)} calendar feeds covering {len(events)} events")


if __name__ == "__main__":
    main()
