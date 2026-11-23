"""Minimal GTFS loader -> flat list of connections for the connection scan.

Works on any GTFS folder (real DART feed or the synthetic one written by synth.py).
Times are minutes since midnight of the service date (GTFS may exceed 24:00).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import pandas as pd

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_hms(s: str) -> float:
    h, m, sec = (int(x) for x in str(s).strip().split(":"))
    return h * 60 + m + sec / 60.0


@dataclass
class Network:
    stops: pd.DataFrame        # stop_id, stop_lat, stop_lon
    connections: pd.DataFrame  # trip_id, dep_stop, arr_stop, dep, arr (sorted by dep)


def active_services(folder: Path, service_date: date) -> set[str]:
    cal = pd.read_csv(folder / "calendar.txt", dtype=str) if (folder / "calendar.txt").exists() else None
    cd = pd.read_csv(folder / "calendar_dates.txt", dtype=str) if (folder / "calendar_dates.txt").exists() else None
    ymd = service_date.strftime("%Y%m%d")
    active: set[str] = set()
    if cal is not None:
        day = WEEKDAYS[service_date.weekday()]
        ok = cal[(cal[day] == "1") & (cal["start_date"] <= ymd) & (cal["end_date"] >= ymd)]
        active |= set(ok["service_id"])
    if cd is not None:
        today = cd[cd["date"] == ymd]
        active |= set(today[today["exception_type"] == "1"]["service_id"])
        active -= set(today[today["exception_type"] == "2"]["service_id"])
    return active


def load_gtfs(folder: str | Path, service_date: date) -> Network:
    folder = Path(folder)
    stops = pd.read_csv(folder / "stops.txt", dtype={"stop_id": str})
    if "stop_name" not in stops.columns:
        stops["stop_name"] = stops["stop_id"]
    stops = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]]
    route_name = {}
    if (folder / "routes.txt").exists():
        rt = pd.read_csv(folder / "routes.txt", dtype=str).fillna("")
        for r in rt.itertuples():
            short = getattr(r, "route_short_name", "") or getattr(r, "route_long_name", "") or r.route_id
            route_name[r.route_id] = short
    trips = pd.read_csv(folder / "trips.txt", dtype=str)
    trips = trips[trips["service_id"].isin(active_services(folder, service_date))]
    st = pd.read_csv(folder / "stop_times.txt", dtype={"trip_id": str, "stop_id": str})
    st = st[st["trip_id"].isin(trips["trip_id"])].copy()
    # real feeds may leave non-timepoint times blank: fill from the other column, then interpolate
    st["arrival_time"] = st["arrival_time"].fillna(st["departure_time"])
    st["departure_time"] = st["departure_time"].fillna(st["arrival_time"])
    st["arr"] = st["arrival_time"].map(lambda v: parse_hms(v) if isinstance(v, str) and v.strip() else float("nan"))
    st["dep"] = st["departure_time"].map(lambda v: parse_hms(v) if isinstance(v, str) and v.strip() else float("nan"))
    st = st.sort_values(["trip_id", "stop_sequence"])
    for col in ("arr", "dep"):
        st[col] = st.groupby("trip_id")[col].transform(lambda x: x.interpolate(limit_direction="both"))
    nxt = st.groupby("trip_id").shift(-1)
    trip_route = dict(zip(trips["trip_id"], trips["route_id"]))
    conn = pd.DataFrame({
        "trip_id": st["trip_id"], "route": st["trip_id"].map(lambda t: route_name.get(trip_route.get(t), trip_route.get(t))), "dep_stop": st["stop_id"], "arr_stop": nxt["stop_id"],
        "dep": st["dep"], "arr": nxt["arr"],
    }).dropna()
    conn = conn.sort_values("dep").reset_index(drop=True)
    return Network(stops=stops.reset_index(drop=True), connections=conn)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
