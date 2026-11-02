"""
capture.py

Saves the raw data behind Cheltenham Open Data's histories, for sources that
keep no history of their own. Each source's file is cut to the area around
Cheltenham with every field kept, and rewritten only when its content changes,
so the git history of sources/<id>/ is the archive.

    python capture.py            # every source
    python capture.py fuel-finder nged-power-cuts

Each run is recorded in status.json (last_ok, failing_since, last_error, as
the site's fetch_status.py does), which the Cloudflare watchdog reads to
email when a capture keeps failing. Exits 1 if any source failed, after the
others have run.
"""

import csv
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "status.json"

CENTRE = (51.8994, -2.0783)  # Cheltenham town centre, on the Promenade
RADIUS_MILES = 25            # wider than any of the site's own search radii
USER_AGENT = "CheltenhamOpenData-raw/1.0 (+https://cheltenham-od.uk)"
MAX_ERROR = 300
RETRY_SECONDS = 10  # one more try after a failure, for a source's brief hiccups


# ---------------------------------------------------------------- helpers

def miles(lat, lon):
    lat1, lon1 = map(math.radians, CENTRE)
    lat2, lon2 = math.radians(lat), math.radians(lon)
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def nearby(lat, lon):
    try:
        return miles(float(lat), float(lon)) <= RADIUS_MILES
    except (TypeError, ValueError):
        return False


def get(url, headers=None, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def csv_rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def to_csv(rows, fields):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def to_json(data):
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


# ---------------------------------------------------------------- cutting each source to our area

def cut_fuel(text):
    """The Fuel Finder CSV: forecourts within RADIUS_MILES, by their coordinates."""
    rows = csv_rows(text)
    fields = list(rows[0]) if rows else []
    keep = [r for r in rows if nearby(r.get("forecourts.location.latitude"), r.get("forecourts.location.longitude"))]
    keep.sort(key=lambda r: r["forecourts.node_id"])
    return to_csv(keep, fields)


def cut_power(text):
    """NGED's live power cuts CSV: cuts within RADIUS_MILES, by their coordinates."""
    rows = csv_rows(text)
    fields = list(rows[0]) if rows else []
    keep = [r for r in rows if nearby(r.get("location_latitude"), r.get("location_longitude"))]
    return to_csv(keep, fields)


BUS_TERMS = ("gloucestershire", "cheltenham", "stagecoach", "go-ahead", "national express", "marchants",
             "bennetts", "first west of england", "pulham", "red & white")


def cut_bus_disruptions(zip_bytes):
    """The BODS disruptions CSV from the catalogue zip: rows that mention our
    councils or an operator serving Cheltenham anywhere in them."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        name = next(n for n in archive.namelist() if n.endswith("disruptions_data_catalogue.csv"))
        text = archive.read(name).decode("utf-8-sig")
    rows = csv_rows(text)
    fields = list(rows[0]) if rows else []
    keep = [r for r in rows if any(t in " ".join(r.values()).lower() for t in BUS_TERMS)]
    return to_csv(keep, fields)


def pos_points(obj):
    """Every (lat, lon) in a DATEX II posList, anywhere in obj."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "posList" and isinstance(value, str):
                nums = [float(n) for n in value.split()]
                yield from zip(nums[0::2], nums[1::2])
            else:
                yield from pos_points(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from pos_points(value)


def cut_closures(raw):
    """National Highways closures: situations with any point within RADIUS_MILES.
    The publication time changes on every call, so it is dropped."""
    payload = json.loads(raw)["D2Payload"]
    situations = [s for s in payload.get("situation", []) if any(nearby(*p) for p in pos_points(s))]
    situations.sort(key=lambda s: s.get("idG") or "")
    return to_json({"situation": situations})


def cut_flood(raw):
    """EA flood warnings in force across England (a short list), without the
    response's metadata."""
    items = json.loads(raw).get("items", [])
    items.sort(key=lambda i: i.get("@id") or "")
    return to_json({"items": items})


def cut_feed_times(raw):
    """An RSS feed without the channel's build and publish times, which change
    on every call. Each item keeps its own."""
    text = raw.decode("utf-8")
    if "<rss" not in text[:500]:
        raise RuntimeError("not an RSS feed")
    channel_end = text.find("<item")
    head, rest = (text, "") if channel_end == -1 else (text[:channel_end], text[channel_end:])
    return re.sub(r"\s*<(lastBuildDate|pubDate)>[^<]*</\1>", "", head) + rest


def cut_warnings(raw):
    """The Met Office South West warnings RSS."""
    return cut_feed_times(raw)


def cut_overflows(raw):
    """Severn Trent storm overflows within RADIUS_MILES, as GeoJSON features."""
    body = json.loads(raw)
    if "features" not in body:
        raise RuntimeError(f"no features in the storm overflow response: {str(body)[:200]}")
    features = sorted(body["features"], key=lambda f: json.dumps(f.get("properties"), sort_keys=True))
    return to_json({"features": features})


def cut_fire_severity(squares_raw, issued_raw):
    """The Fire Severity Index for each 10 km square within RADIUS_MILES and
    each forecast day, with when the Met Office issued it."""
    squares, issued = json.loads(squares_raw), json.loads(issued_raw)
    for body in (squares, issued):
        if "error" in body:
            raise RuntimeError(f"Fire Severity Index query failed: {body['error']}")
    rows = sorted((f["attributes"] for f in squares.get("features", [])),
                  key=lambda a: (str(a.get("square_reference_pk")), a.get("data_date_offset_pk") or 0))
    return to_json({"issued": [f["attributes"] for f in issued.get("features", [])], "squares": rows})


def cut_rail(raw):
    """The Cheltenham Spa departure and arrival board, every field kept except
    generatedAt, which changes on every call. A board showing only rail
    replacement buses is how the line being closed shows up."""
    board = json.loads(raw)
    if board.get("crs") != "CNM":
        raise RuntimeError(f"not the Cheltenham Spa board: {str(board)[:200]}")
    board.pop("generatedAt", None)
    return to_json(board)


def cut_toilets(raw):
    """The Great British Toilet Map export: toilets within RADIUS_MILES."""
    data = json.loads(raw)
    toilets = data if isinstance(data, list) else data.get("toilets") or data.get("data") or []

    def coords(t):
        loc = t.get("location") or {}
        if isinstance(loc, dict) and "coordinates" in loc:
            lon, lat = loc["coordinates"][:2]
            return lat, lon
        return t.get("latitude") or loc.get("lat"), t.get("longitude") or loc.get("lng")

    keep = [t for t in toilets if nearby(*coords(t))]
    keep.sort(key=lambda t: str(t.get("id") or ""))
    return to_json(keep)


# ---------------------------------------------------------------- fetching

def fetch_fuel():
    url, token = os.environ.get("FUEL_PROXY_URL"), os.environ.get("FUEL_PROXY_TOKEN")
    if not url or not token:
        raise RuntimeError("FUEL_PROXY_URL and FUEL_PROXY_TOKEN are required")
    return cut_fuel(get(url, {"Authorization": f"Bearer {token}"}, timeout=180).decode("utf-8-sig"))


def fetch_closures():
    key = os.environ.get("NAT_HIGH_KEY")
    if not key:
        raise RuntimeError("NAT_HIGH_KEY is required")
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    query = urllib.parse.urlencode({"closureType": "unplanned",
                                    "startDateTime": now.replace(hour=0, minute=0, second=0).isoformat(),
                                    "endDateTime": now.isoformat()})
    raw = get(f"https://api.data.nationalhighways.co.uk/roads/v2.0/closures?{query}",
              {"Ocp-Apim-Subscription-Key": key, "X-Response-MediaType": "application/json"})
    return cut_closures(raw)


def arcgis(url, params):
    return get(f"{url}?{urllib.parse.urlencode(params)}")


def fetch_overflows():
    return cut_overflows(arcgis(
        "https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/"
        "Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query", {
            "where": "1=1", "outFields": "*", "f": "geojson",
            "geometry": json.dumps({"x": CENTRE[1], "y": CENTRE[0], "spatialReference": {"wkid": 4326}}),
            "geometryType": "esriGeometryPoint", "inSR": 4326, "distance": RADIUS_MILES,
            "units": "esriSRUnit_StatuteMile", "spatialRel": "esriSpatialRelIntersects"}))


FSI = "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/OASYS_FSI_PRD_VIEW/FeatureServer"


def fetch_fire_severity():
    squares = arcgis(f"{FSI}/0/query", {
        "geometry": f"{CENTRE[1]},{CENTRE[0]}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "distance": round(RADIUS_MILES * 1609.344), "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false", "f": "json"})
    issued = arcgis(f"{FSI}/1/query", {"where": "language='DEFAULT'", "outFields": "*", "f": "json"})
    return cut_fire_severity(squares, issued)


def fetch_rail():
    key = os.environ.get("RDM_LDBWS_KEY")
    if not key:
        raise RuntimeError("RDM_LDBWS_KEY is required")
    return cut_rail(get(
        "https://api1.raildata.org.uk/1010-live-arrival-and-departure-boards-arr-and-dep1_1/LDBWS/api/20220120"
        "/GetArrDepBoardWithDetails/CNM?numRows=10", {"x-apikey": key}, timeout=30))


def fetch_toilets():
    page = get("https://www.toiletmap.org.uk/dataset").decode("utf-8")
    links = re.findall(r'href=["\']([^"\']*?/exports/[^"\']*?\.json[^"\']*)["\']', page)
    if not links:
        raise RuntimeError("no JSON export link on the Toilet Map dataset page")
    return cut_toilets(get(links[0].replace("&amp;", "&"), timeout=180))


# id: (output file, fetch function returning the text to save)
SOURCES = {
    "fuel-finder": ("forecourts.csv", fetch_fuel),
    "nged-power-cuts": ("power-cuts.csv", lambda: cut_power(get(
        "https://connecteddata.nationalgrid.co.uk/dataset/d6672e1e-c684-4cea-bb78-c7e5248b62a2/"
        "resource/a1365982-4e05-463c-8304-8323a2ba0ccd/download/live_detailed_power_cuts.csv").decode("utf-8-sig"))),
    "bods-disruptions": ("disruptions.csv", lambda: cut_bus_disruptions(get(
        "https://data.bus-data.dft.gov.uk/catalogue/", timeout=300))),
    "national-highways-closures": ("closures.json", fetch_closures),
    "ea-flood-warnings": ("floods.json", lambda: cut_flood(get(
        "https://environment.data.gov.uk/flood-monitoring/id/floods", {"Accept": "application/json"}))),
    "met-office-warnings": ("south-west.xml", lambda: cut_warnings(get(
        "https://www.metoffice.gov.uk/public/data/PWSCache/WarningsRSS/Region/sw"))),
    "toilet-map": ("toilets.json", fetch_toilets),
    "severn-trent-storm-overflows": ("overflows.json", fetch_overflows),
    "fire-severity-index": ("fire-severity.json", fetch_fire_severity),
    "rail-cheltenham-spa": ("board.json", fetch_rail),
    "gcc-school-closures": ("closures.xml", lambda: cut_feed_times(get(
        "https://www.gloucestershire.gov.uk/api/pcg-emergency-school-closures/rss-feed/get"))),
}

# Sources that change at most daily: captured until they succeed each day,
# rather than on every 15-minute run.
DAILY = {"toilet-map"}


# ---------------------------------------------------------------- status

def update(record, ok, now, error):
    if ok:
        return {"last_ok": now.date().isoformat(), "failing_since": None, "last_error": None}
    return {"last_ok": record.get("last_ok"),
            "failing_since": record.get("failing_since") or now.strftime("%Y-%m-%dT%H:%MZ"),
            "last_error": error}


def save(source_id, filename, text):
    """Write the file only if it changed. Returns True when it did."""
    path = ROOT / "sources" / source_id / filename
    data = text.encode("utf-8")  # compared as bytes, so Windows line endings in a feed still match
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def main(argv=None, now=None):
    named = sys.argv[1:] if argv is None else argv
    now = now or datetime.now(timezone.utc)
    try:
        status = json.loads(STATUS.read_text())
    except (OSError, ValueError):
        status = {}
    scripts = dict(status.get("scripts", {}))  # a copy, so the change check below compares old with new
    today = now.date().isoformat()
    names = named or [n for n in SOURCES if n not in DAILY or scripts.get(n, {}).get("last_ok") != today]
    failed = []
    for name in names:
        filename, fetch = SOURCES[name]
        try:
            try:
                text = fetch()
            except Exception:  # pylint: disable=broad-except
                time.sleep(RETRY_SECONDS)
                text = fetch()
            changed = save(name, filename, text)
            scripts[name] = update(scripts.get(name, {}), True, now, None)
            print(f"{name}: {'changed' if changed else 'unchanged'}")
        except Exception as exc:  # pylint: disable=broad-except
            error = re.sub(r"\?[^\s'\"]*", "?…", f"{type(exc).__name__}: {exc}")[:MAX_ERROR]
            scripts[name] = update(scripts.get(name, {}), False, now, error)
            failed.append(name)
            print(f"{name}: FAILED {error}", file=sys.stderr)
    new = {"runner": "raw", "scripts": dict(sorted(scripts.items()))}
    if new != status:
        STATUS.write_text(json.dumps(new, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
