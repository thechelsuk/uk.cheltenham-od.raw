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
| Trains at Cheltenham Spa | `sources/rail-cheltenham-spa/board.json` | [Rail Delivery Group](https://raildata.org.uk/) (National Rail Enquiries' Live Arrival and Departure Boards), via the Rail Data Marketplace | Rail Data Marketplace open licence: may be made freely available and retained, attributed to Rail Delivery Group |
| Public toilets | `sources/toilet-map/toilets.json` | [The Great British Toilet Map](https://www.toiletmap.org.uk/dataset) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Council payments to suppliers | `sources/cbc-payments-to-suppliers/YYYY-MM.csv` | [Cheltenham Borough Council](https://www.cheltenham.gov.uk/about-the-council/council-performance-and-spending/financial-information/payments-to-suppliers-and-procurement-card-purchases/) | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), per the council's [data.gov.uk record](https://www.data.gov.uk/dataset/local_authority_spend_over_500_cheltenham) |
| Storm overflows | `sources/severn-trent-storm-overflows/overflows.json` | [Severn Trent Water](https://www.stwater.co.uk/in-my-area/storm-overflow-map/), via the Water UK National Storm Overflow Hub | None stated |
| Fire severity | `sources/fire-severity-index/fire-severity.json` | Met Office Fire Severity Index, published by [Natural England](https://openaccess.naturalengland.org.uk/) | None stated |
| School closures | `sources/gcc-school-closures/closures.xml` | [Gloucestershire County Council](https://www.gloucestershire.gov.uk/closures/) | None stated |
| Business rates lists | `sources/cbc-business-rates/YYYY-MM-empty.xlsx`, `YYYY-MM-occupied.xlsx` | [Cheltenham Borough Council](https://www.cheltenham.gov.uk/business-and-licensing/business-rates-and-rate-relief/business-rates-data/) | None stated |

Contains public sector information licensed under the Open Government Licence v3.0. Contains data from Rail Delivery Group, the Met Office, National Grid Electricity Distribution and The Great British Toilet Map.

The last four state no licence. Their publishers make them freely available as public information, and they are kept here as a public record, not for commercial use. A publisher who would like its data removed can open an issue.

The council payments files are the council's own monthly files from April 2016 to September 2026, kept as published, one per month. April 2016 to December 2019 came from the web archive's copies of the council's old pages, as its current site lists January 2020 onwards. A month the council reissued is kept as `YYYY-MM-revised.csv` beside the original, and February 2019 survives only as `.xls`. They were added once and are not part of the regular capture.

The business rates lists are the council's lists of occupied and empty business properties, kept as published, with the names the council chose to publish (it leaves out sole traders and individuals). Releases from June 2022 come from the web archive's copies of the council's old site. The June 2026 occupied list isn't kept, as it holds ratepayers' billing addresses. Missing releases are listed in `sources/cbc-business-rates/README.md`. They were added once and are not part of the regular capture.

The trains file is the station's departure and arrival board, which changes on most runs; a board showing only rail replacement buses is how a line closure appears. The flood warnings, weather warnings and school closures files hold everything in force across their area, as each is a short list. Fire severity is kept per 10 km grid square, without the squares' shapes, which never change. The bus disruptions file keeps rows that name Gloucestershire, Cheltenham or an operator serving the town.

## Running It

```bash
python capture.py                  # every source due
python capture.py fuel-finder      # one source
python -m pytest                   # offline tests
```

Fuel prices need `FUEL_PROXY_URL` and `FUEL_PROXY_TOKEN`, as Fuel Finder refuses GitHub's runners. Road closures need `NAT_HIGH_KEY`, and trains need `RDM_LDBWS_KEY`.

The code is under the MIT Licence; each data file stays under its publisher's licence above.
