# Cheltenham Open Data: Raw Downloads

Copies of the raw data that [Cheltenham Open Data](https://cheltenham-od.uk) uses from sources that keep no history of their own, such as live fuel prices and road closures. If one of the site's data scripts goes wrong, its history can be rebuilt from these copies.

## How It Works

- `capture.py` downloads each source, keeps only what lies within 25 miles of Cheltenham town centre, with every field as published, and saves it to `sources/<source>/`.
- A file is rewritten only when its content changes, so the **git history of each file is the archive**. To see a source on a past date, read that file at the last commit before it, for example `git log -- sources/fuel-finder/forecourts.csv`.
- The capture runs every 15 minutes, started by a Cloudflare Worker, with an hourly GitHub schedule as a backup. Daily sources are captured once a day.
- `status.json` records when each source last worked and since when it has been failing. An email goes out when one has been failing for over an hour.

## Sources and Licences

| Source | File | Publisher | Licence |
| --- | --- | --- | --- |
| Fuel prices | `sources/fuel-finder/forecourts.csv` | [Fuel Finder](https://www.gov.uk/guidance/access-fuel-price-data), Department for Energy Security and Net Zero | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |
| Unplanned road closures | `sources/national-highways-closures/closures.json` | [National Highways](https://developer.data.nationalhighways.co.uk/) | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |
| Bus disruptions | `sources/bods-disruptions/disruptions.csv` | [Bus Open Data Service](https://data.bus-data.dft.gov.uk/), Department for Transport | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |
| Power cuts | `sources/nged-power-cuts/power-cuts.csv` | [National Grid Electricity Distribution](https://connecteddata.nationalgrid.co.uk/dataset/live-power-cuts) | NGED Open Data Licence |
| Flood warnings | `sources/ea-flood-warnings/floods.json` | [Environment Agency](https://environment.data.gov.uk/flood-monitoring/doc/reference) | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |
| Weather warnings | `sources/met-office-warnings/south-west.xml` | [Met Office](https://www.metoffice.gov.uk/weather/warnings-and-advice/uk-warnings) | Met Office RSS terms: free for any purpose, attributed to the Met Office |
| Public toilets | `sources/toilet-map/toilets.json` | [The Great British Toilet Map](https://www.toiletmap.org.uk/dataset) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Storm overflows | `sources/severn-trent-storm-overflows/overflows.json` | [Severn Trent Water](https://www.stwater.co.uk/in-my-area/storm-overflow-map/), via the Water UK National Storm Overflow Hub | None stated |
| Fire severity | `sources/fire-severity-index/fire-severity.json` | Met Office Fire Severity Index, published by [Natural England](https://openaccess.naturalengland.org.uk/) | None stated |
| School closures | `sources/gcc-school-closures/closures.xml` | [Gloucestershire County Council](https://www.gloucestershire.gov.uk/closures/) | None stated |

Contains public sector information licensed under the Open Government Licence v3.0. Contains data from the Met Office, National Grid Electricity Distribution and The Great British Toilet Map.

The last three state no licence. Their publishers make them freely available as public information, and they are kept here as a public record, not for commercial use. A publisher who would like its data removed can open an issue.

The flood warnings, weather warnings and school closures files hold everything in force across their area, as each is a short list. Fire severity is kept per 10 km grid square, without the squares' shapes, which never change. The bus disruptions file keeps rows that name Gloucestershire, Cheltenham or an operator serving the town.

## Running It

```bash
python capture.py                  # every source due
python capture.py fuel-finder      # one source
python -m pytest                   # offline tests
```

Fuel prices need `FUEL_PROXY_URL` and `FUEL_PROXY_TOKEN`, as Fuel Finder refuses GitHub's runners. Road closures need `NAT_HIGH_KEY`.

The code is under the MIT Licence; each data file stays under its publisher's licence above.
