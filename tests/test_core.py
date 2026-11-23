import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from pantrynet import synth, gtfs, csa, analysis


def _router(tmp_path):
    synth.make_gtfs(tmp_path / "g")
    net = gtfs.load_gtfs(tmp_path / "g", date(2026, 12, 2))  # a Wednesday
    return csa.Router(net)


def test_parse_hms_over_24h():
    assert gtfs.parse_hms("25:30:00") == 25 * 60 + 30


def test_weekend_has_no_service(tmp_path):
    synth.make_gtfs(tmp_path / "g")
    net = gtfs.load_gtfs(tmp_path / "g", date(2026, 12, 5))  # Saturday
    assert len(net.connections) == 0


def test_arrival_monotone_in_departure(tmp_path):
    r = _router(tmp_path)
    lat, lon = r.lat[0], r.lon[0]
    a = r.earliest_arrivals(lat, lon, 600)
    b = r.earliest_arrivals(lat, lon, 630)
    assert (b >= a - 1e-9).all()


def test_later_departure_never_arrives_earlier_than_departure(tmp_path):
    r = _router(tmp_path)
    arr = r.earliest_arrivals(r.lat[10], r.lon[10], 700)
    assert (arr[arr < float("inf")] >= 700).all()


def test_shift_keeps_duration(tmp_path):
    p = synth.make_pantries(tmp_path / "p.csv")
    q = analysis.shift_window(p, "P01", 30)
    d0 = p.loc[0, "close_min"] - p.loc[0, "open_min"]
    d1 = q.loc[0, "close_min"] - q.loc[0, "open_min"]
    assert d0 == d1 and q.loc[0, "open_min"] == p.loc[0, "open_min"] + 30


def test_extending_checkin_creates_backup_when_slack_matches(tmp_path):
    r = _router(tmp_path)
    p = synth.make_pantries(tmp_path / "p.csv")
    sc = analysis.scenario_table(r, p)
    fix = analysis.smallest_fix(sc)
    # apply the smallest fix on one near-miss pair and confirm the backup appears
    row = fix[~fix.already_has_backup].iloc[0]
    p2 = p.copy(); p2["last_checkin_min"] = p2["last_checkin_min"].astype(float); m = p2.pantry_id == row.dest
    p2.loc[m, "last_checkin_min"] += row.min_extension_min + 1e-6
    sc2 = analysis.scenario_table(r, p2)
    sel = (sc2.origin == row.origin) & (sc2.dest == row.dest)
    assert sc2[sel].backup.any()


def test_eligibility_blocks_backup():
    from types import SimpleNamespace as N
    a, b, c = N(eligible_zips="75217;75227"), N(eligible_zips="75231"), N(eligible_zips="ALL")
    assert not analysis.eligible_overlap(a, b)
    assert analysis.eligible_overlap(a, c) and analysis.eligible_overlap(a, N(eligible_zips="75227"))


def test_arriving_hours_before_opening_is_not_a_backup(tmp_path):
    r = _router(tmp_path)
    p = synth.make_pantries(tmp_path / "p.csv")
    sc = analysis.scenario_table(r, p)
    # any scenario that arrives more than max_wait before the destination opens must not count
    early = sc[sc.too_early]
    assert not early.backup.any()
    # and with waiting allowed to be unlimited there can only be more backups, never fewer
    r2 = csa.Router(r.net, csa.Params(max_wait_min=1e9))
    sc2 = analysis.scenario_table(r2, p)
    assert sc2.backup.sum() >= sc.backup.sum()


def test_walking_transfer_between_nearby_stops():
    import numpy as np
    from pantrynet.gtfs import Network
    lat0, lon0 = 32.70, -96.90
    stops = pd.DataFrame({"stop_id": ["A", "B", "B2", "C"], "stop_name": ["A", "B", "B2", "C"],
                          "stop_lat": [lat0, lat0, lat0 + 0.0015, lat0 + 0.02],   # B2 is ~170 m from B
                          "stop_lon": [lon0, lon0 + 0.02, lon0 + 0.02, lon0 + 0.02]})
    conn = pd.DataFrame([
        {"trip_id": "t1", "route": "R1", "dep_stop": "A", "arr_stop": "B", "dep": 600.0, "arr": 610.0},
        {"trip_id": "t2", "route": "R2", "dep_stop": "B2", "arr_stop": "C", "dep": 615.0, "arr": 625.0},
    ])
    net = Network(stops=stops, connections=conn)
    walkless = csa.Router(net, csa.Params(footpath_km=0))
    with_walk = csa.Router(net, csa.Params(footpath_km=0.4))
    arr0 = walkless.earliest_arrivals(lat0, lon0, 595)
    arr1 = with_walk.earliest_arrivals(lat0, lon0, 595)
    ic = with_walk.idx["C"]
    assert arr0[ic] == float("inf") and arr1[ic] == 625.0
    ex = with_walk.explain((lat0, lon0), 595, (lat0 + 0.02, lon0 + 0.02))
    assert [l["route"] for l in ex["legs"]] == ["R1", "R2"] and ex["legs"][1]["transfer"] == "foot"
