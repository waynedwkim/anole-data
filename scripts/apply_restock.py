#!/usr/bin/env python3
"""Merge hand-verified show dates into events.json.

The weekly refresh can only refill the five series that publish a machine-
readable schedule; the other thirty are read by a person (or an agent) and
have to be merged back by hand. This is the hand. It takes a JSON file of
candidates that already passed source verification and applies the last few
checks that a verifier reading one page at a time cannot make:

  * the date is not already on the calendar (by series+date+city, and by the
    refresh script's own natural key so a later automated pass will not
    duplicate it under a different id);
  * the state is one the series has actually run in before, unless the
    candidate is explicitly allowed -- research agents share a browser and
    can read each other's pages, so a right date filed under the wrong
    series is the failure to catch here;
  * the accepted-basis rule from DIFFERENTIATION.md: organizer page, venue
    calendar, or the organizer's own Facebook. Aggregators never.

Usage:
  python scripts/apply_restock.py candidates.json [--today YYYY-MM-DD] [--allow-state SERIES:ST ...] [--dry-run]

Candidates are objects with: seriesId, startDate, endDate ("" for one day),
city, state, venue, title, sourceUrl, basis, quote.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events.json"
ROSTER = ROOT / "series_roster.json"
ACCEPTED_BASIS = {"organizer-page", "venue-calendar", "facebook-official"}
STATE_RE = re.compile(r"^[A-Z]{2}$")


def slugify(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def natural_key(event):
    title = re.sub(r"[^a-z0-9]+", "", (event.get("title") or "").lower())
    return (event["startDate"], event.get("state"), title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--allow-state", action="append", default=[],
                    help="SERIES:ST to accept a state the series has not used before")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    events = json.loads(EVENTS.read_text())
    roster = {s["id"]: s for s in json.loads(ROSTER.read_text())}
    candidates = json.loads(Path(args.candidates).read_text())
    if isinstance(candidates, dict):
        candidates = candidates.get("confirmed", [])

    have = {(e["seriesId"], e["startDate"], slugify(e.get("city") or "")) for e in events}
    have_natural = {natural_key(e) for e in events}
    states_by_series = defaultdict(set)
    for e in events:
        if e.get("state"):
            states_by_series[e["seriesId"]].add(e["state"])
    allowed = defaultdict(set)
    for item in args.allow_state:
        sid, st = item.split(":")
        allowed[sid].add(st.upper())

    added, held, skipped = [], [], []
    for c in candidates:
        sid = c.get("seriesId")
        why = None
        if sid not in roster:
            why = "unknown series"
        elif c.get("basis") not in ACCEPTED_BASIS:
            why = f"basis {c.get('basis')!r} not accepted"
        elif not re.match(r"^\d{4}-\d{2}-\d{2}$", c.get("startDate") or ""):
            why = "bad startDate"
        elif c["startDate"] < args.today:
            why = "in the past"
        elif not STATE_RE.match(c.get("state") or ""):
            why = f"bad state {c.get('state')!r}"
        elif not (c.get("city") or "").strip():
            why = "no city"
        elif not (c.get("sourceUrl") or "").startswith("http"):
            why = "no source url"
        if why:
            skipped.append((c, why))
            continue

        key = (sid, c["startDate"], slugify(c["city"]))
        if key in have:
            skipped.append((c, "already on the calendar"))
            continue

        known = states_by_series.get(sid, set())
        if known and c["state"] not in known and c["state"] not in allowed[sid]:
            held.append((c, f"state {c['state']} never seen for this series (known: {sorted(known)})"))
            continue

        end = (c.get("endDate") or "").strip() or None
        if end and end < c["startDate"]:
            skipped.append((c, "endDate before startDate"))
            continue
        title = (c.get("title") or "").strip() or f"{roster[sid]['name']} {c['city']}"
        event = {
            "id": f"{sid}-{slugify(c['city'])}-{c['startDate']}",
            "seriesId": sid,
            "title": title,
            "city": c["city"].strip(),
            "state": c["state"],
            "venue": (c.get("venue") or "").strip() or None,
            "startDate": c["startDate"],
            "endDate": end,
            "url": roster[sid].get("website") or c["sourceUrl"],
            "source": c["sourceUrl"],
            "checkedAt": args.today,
        }
        if natural_key(event) in have_natural:
            skipped.append((c, "same show already on the calendar under another id"))
            continue
        have.add(key)
        have_natural.add(natural_key(event))
        added.append(event)

    print(f"candidates={len(candidates)} added={len(added)} held={len(held)} skipped={len(skipped)}")
    for c, why in held:
        print(f"  HOLD  {c['seriesId']:34} {c['startDate']} {c['city']}, {c['state']}  -- {why}")
    for c, why in skipped:
        if why != "already on the calendar":
            print(f"  SKIP  {c.get('seriesId','?'):34} {c.get('startDate','?')} {c.get('city','?')}  -- {why}")
    for e in added:
        print(f"  ADD   {e['seriesId']:34} {e['startDate']}..{e['endDate'] or '-'} {e['city']}, {e['state']}  <- {e['source']}")

    if args.dry_run or not added:
        return
    merged = events + added
    merged.sort(key=lambda e: (e["startDate"], e["id"]))
    EVENTS.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")

    # Recompute health.json with the refresh script's own function so the
    # numbers on the site and in the alarm come from one place.
    sys.path.insert(0, str(ROOT / "scripts"))
    import refresh_events  # noqa: E402
    refresh_events.write_health(merged, date.fromisoformat(args.today))


if __name__ == "__main__":
    main()
