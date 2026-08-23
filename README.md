# scalespot-data

Public data feed for the [ScaleSpot](https://github.com/waynedwkim/scalespot) iOS app (US reptile shop & expo finder).

- `events.json` — upcoming US reptile expo events. The app fetches this at launch, so updating this file updates every installed app without an App Store release.

## events.json schema

```json
{
  "id": "repticon-tampa-2026-09-12",
  "seriesId": "repticon",
  "title": "Repticon Tampa",
  "city": "Tampa",
  "state": "FL",
  "venue": "Florida State Fairgrounds",
  "startDate": "2026-09-12",
  "endDate": "2026-09-13",
  "url": "https://repticon.com/florida/tampa/",
  "source": "https://repticon.com/show-calendar/"
}
```

Every event must carry a `source` URL where the date is verifiable. Events are curated from official organizer calendars; automated refresh via scheduled scraping is planned.

## Submissions

Run a show or shop we should list? Email kjs140611@gmail.com.
