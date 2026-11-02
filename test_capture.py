"""Offline tests for capture.py. Run: python -m pytest"""
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

import capture

NEAR = ("51.90", "-2.08")     # Cheltenham
FAR = ("53.48", "-2.24")      # Manchester
NOW = datetime(2026, 11, 2, 11, 30, tzinfo=timezone.utc)


def test_fuel_keeps_nearby_forecourts_with_every_column():
    text = ("forecourts.node_id,forecourts.location.latitude,forecourts.location.longitude,price\n"
            f"b,{NEAR[0]},{NEAR[1]},170.9\n"
            f"x,{FAR[0]},{FAR[1]},160.9\n"
            f"a,{NEAR[0]},{NEAR[1]},171.9\n")
    out = capture.cut_fuel(text).splitlines()
    assert out[0] == "forecourts.node_id,forecourts.location.latitude,forecourts.location.longitude,price"
    assert [line.split(",")[0] for line in out[1:]] == ["a", "b"]


def test_power_cuts_without_coordinates_are_left_out():
    text = f"id,location_latitude,location_longitude\n1,{NEAR[0]},{NEAR[1]}\n2,,\n3,{FAR[0]},{FAR[1]}\n"
    assert [r["id"] for r in capture.csv_rows(capture.cut_power(text))] == ["1"]


def test_bus_disruptions_keep_rows_naming_our_council_or_operators():
    rows = "organisation,summary\nGloucestershire County Council,x\nLeeds,Stagecoach West diversion\nLeeds,y\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("catalogue/disruptions_data_catalogue.csv", rows)
    out = capture.csv_rows(capture.cut_bus_disruptions(buffer.getvalue()))
    assert [r["summary"] for r in out] == ["x", "Stagecoach West diversion"]


def test_closures_keep_nearby_situations_and_drop_the_publication_time():
    near = {"idG": "1", "situationRecord": [{"r": {"locationReference": {"posList": f"{NEAR[0]} {NEAR[1]}"}}}]}
    far = {"idG": "2", "situationRecord": [{"r": {"locationReference": {"posList": f"{FAR[0]} {FAR[1]}"}}}]}
    raw = json.dumps({"D2Payload": {"publicationTime": "2026-11-02T11:30:00Z", "situation": [far, near]}})
    assert json.loads(capture.cut_closures(raw)) == {"situation": [near]}


def test_flood_drops_metadata():
    raw = json.dumps({"meta": {"publisher": "EA"}, "items": [{"@id": "b"}, {"@id": "a"}]}).encode()
    assert json.loads(capture.cut_flood(raw)) == {"items": [{"@id": "a"}, {"@id": "b"}]}


def test_warnings_drop_the_feed_times_but_keep_each_warnings_own():
    raw = (b"<rss><channel><lastBuildDate>Mon, 02 Nov</lastBuildDate><pubDate>Mon, 02 Nov</pubDate>"
           b"<item><title>Rain</title><pubDate>Sun, 01 Nov</pubDate></item></channel></rss>")
    out = capture.cut_warnings(raw)
    assert "lastBuildDate" not in out and out.count("<pubDate>") == 1 and "Sun, 01 Nov" in out


def test_toilets_read_geojson_style_coordinates():
    data = [{"id": 2, "location": {"coordinates": [float(NEAR[1]), float(NEAR[0])]}},
            {"id": 1, "location": {"coordinates": [float(FAR[1]), float(FAR[0])]}}]
    assert [t["id"] for t in json.loads(capture.cut_toilets(json.dumps(data).encode()))] == [2]


def test_save_writes_only_when_the_content_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    assert capture.save("s", "f.csv", "a\n") is True
    assert capture.save("s", "f.csv", "a\n") is False
    assert capture.save("s", "f.csv", "b\n") is True
    assert capture.save("s", "f.xml", "<rss>\r\n</rss>") is True
    assert capture.save("s", "f.xml", "<rss>\r\n</rss>") is False


def test_a_failure_is_recorded_and_the_others_still_run(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "RETRY_SECONDS", 0)
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    monkeypatch.setattr(capture, "STATUS", tmp_path / "status.json")

    def boom():
        raise RuntimeError("HTTP Error 403: Forbidden for https://x.example/?key=secret")

    monkeypatch.setattr(capture, "SOURCES", {"bad": ("f.txt", boom), "good": ("f.txt", lambda: "ok\n")})
    assert capture.main([], now=NOW) == 1
    status = json.loads((tmp_path / "status.json").read_text())["scripts"]
    assert status["good"] == {"last_ok": "2026-11-02", "failing_since": None, "last_error": None}
    assert status["bad"]["failing_since"] == "2026-11-02T11:30Z"
    assert "secret" not in status["bad"]["last_error"]
    assert (tmp_path / "sources" / "good" / "f.txt").read_text() == "ok\n"


def test_daily_sources_run_until_they_succeed_that_day(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    monkeypatch.setattr(capture, "STATUS", tmp_path / "status.json")
    ran = []
    monkeypatch.setattr(capture, "SOURCES", {
        "live": ("f.txt", lambda: ran.append("live") or "x\n"),
        "daily": ("f.txt", lambda: ran.append("daily") or "y\n"),
    })
    monkeypatch.setattr(capture, "DAILY", {"daily"})
    capture.main([], now=NOW)
    capture.main([], now=NOW.replace(hour=12))
    capture.main([], now=NOW.replace(day=3))
    assert ran == ["live", "daily", "live", "live", "daily"]


def test_feed_times_are_dropped_from_the_channel_only():
    raw = (b"<rss><channel><lastBuildDate>Mon</lastBuildDate>"
           b"<item><title>School A</title><pubDate>Sun</pubDate></item></channel></rss>")
    out = capture.cut_feed_times(raw)
    assert "lastBuildDate" not in out and "<pubDate>Sun</pubDate>" in out


def test_a_page_that_is_not_a_feed_fails():
    with pytest.raises(RuntimeError, match="not an RSS feed"):
        capture.cut_feed_times(b"<html>Service unavailable</html>")


def test_overflows_need_features():
    assert json.loads(capture.cut_overflows(b'{"features": [{"properties": {"id": 1}}]}'))["features"]
    with pytest.raises(RuntimeError):
        capture.cut_overflows(b'{"error": {"code": 400}}')


def test_fire_severity_keeps_each_square_and_day_with_the_issue_time():
    squares = json.dumps({"features": [
        {"attributes": {"square_reference_pk": "SP00", "data_date_offset_pk": 1, "rating": 2}},
        {"attributes": {"square_reference_pk": "SO92", "data_date_offset_pk": 0, "rating": 1}}]})
    issued = json.dumps({"features": [{"attributes": {"received_date": "2026-11-02"}}]})
    out = json.loads(capture.cut_fire_severity(squares, issued))
    assert [s["square_reference_pk"] for s in out["squares"]] == ["SO92", "SP00"]
    assert out["issued"] == [{"received_date": "2026-11-02"}]


def test_an_existing_status_file_records_new_sources_and_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "RETRY_SECONDS", 0)
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    monkeypatch.setattr(capture, "STATUS", tmp_path / "status.json")
    (tmp_path / "status.json").write_text(json.dumps({"runner": "raw", "scripts": {
        "old": {"last_ok": "2026-11-02", "failing_since": None, "last_error": None}}}))

    def boom():
        raise RuntimeError("HTTP Error 500")

    monkeypatch.setattr(capture, "SOURCES", {"old": ("f.txt", boom), "new": ("f.txt", lambda: "x\n")})
    capture.main([], now=NOW)
    status = json.loads((tmp_path / "status.json").read_text())["scripts"]
    assert status["new"]["last_ok"] == "2026-11-02"
    assert status["old"]["failing_since"] == "2026-11-02T11:30Z"


def test_rail_keeps_the_board_without_its_generated_time():
    raw = json.dumps({"crs": "CNM", "generatedAt": "2026-11-02T13:00:00", "busServices": [{"std": "13:10"}]})
    assert json.loads(capture.cut_rail(raw.encode())) == {"crs": "CNM", "busServices": [{"std": "13:10"}]}
    with pytest.raises(RuntimeError):
        capture.cut_rail(b'{"message": "Unauthorized"}')


def test_a_source_that_fails_once_is_tried_again(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "RETRY_SECONDS", 0)
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    monkeypatch.setattr(capture, "STATUS", tmp_path / "status.json")
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("BadZipFile: File is not a zip file")
        return "ok\n"

    monkeypatch.setattr(capture, "SOURCES", {"flaky": ("f.txt", flaky)})
    assert capture.main([], now=NOW) == 0
    assert len(calls) == 2
