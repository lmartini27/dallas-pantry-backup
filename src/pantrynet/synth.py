"""SYNTHETIC data generator. Nothing here describes real Dallas pantries or DART service.

Builds a toy city: a grid of stops, east-west and north-south bus routes with
different headways, and ~12 pantries with made-up windows. Some pairs are
deliberately tuned so near-misses exist (so the analysis has something to find).
Writes a GTFS-format folder so the real loader is exercised end to end.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

LAT0, LON0 = 32.70, -96.90          # arbitrary origin (in the Dallas area, but the city is fake)
KM_LAT = 111.0
KM_LON = 111.0 * np.cos(np.radians(LAT0))


def to_latlon(x_km: float, y_km: float) -> tuple[float, float]:
    return LAT0 + y_km / KM_LAT, LON0 + x_km / KM_LON


def hm(t: float) -> str:
    t = int(round(t * 60))
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def make_gtfs(folder: str | Path, seed: int = 7, grid: int = 7, spacing_km: float = 1.6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    stops = []
    for i in range(grid):
        for j in range(grid):
            lat, lon = to_latlon(i * spacing_km, j * spacing_km)
            stops.append({"stop_id": f"S{i}_{j}", "stop_name": f"Stop {i},{j}", "stop_lat": lat, "stop_lon": lon})
    pd.DataFrame(stops).to_csv(folder / "stops.txt", index=False)

    # routes: some rows and columns, different headways (min) and speeds
    route_defs = []
    for r, hw in [(1, 20), (3, 30), (5, 60)]:
        route_defs.append((f"E{r}", [(i, r) for i in range(grid)], hw, int(rng.integers(0, hw))))
    for c, hw in [(1, 30), (3, 20), (5, 45)]:
        route_defs.append((f"N{c}", [(c, j) for j in range(grid)], hw, int(rng.integers(0, hw))))
    trips, times, routes = [], [], []
    speed_kmh = 22.0
    for rid, path, hw, offset in route_defs:
        routes.append({"route_id": rid, "route_short_name": rid, "route_type": 3})
        for direction, p in ((0, path), (1, path[::-1])):
            t0 = 6 * 60 + offset
            n = 0
            while t0 < 20 * 60:
                tid = f"{rid}_{direction}_{n}"
                trips.append({"route_id": rid, "service_id": "WK", "trip_id": tid})
                t = t0
                for seq, (i, j) in enumerate(p):
                    times.append({"trip_id": tid, "arrival_time": hm(t), "departure_time": hm(t),
                                  "stop_id": f"S{i}_{j}", "stop_sequence": seq})
                    t += spacing_km / speed_kmh * 60 + 0.5
                t0 += hw; n += 1
    pd.DataFrame(routes).to_csv(folder / "routes.txt", index=False)
    pd.DataFrame(trips).to_csv(folder / "trips.txt", index=False)
    pd.DataFrame(times).to_csv(folder / "stop_times.txt", index=False)
    pd.DataFrame([{"service_id": "WK", "monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1,
                   "saturday": 0, "sunday": 0, "start_date": "20200101", "end_date": "20301231"}]
                 ).to_csv(folder / "calendar.txt", index=False)
    return pd.DataFrame(stops)


def make_pantries(path: str | Path, seed: int = 7, n: int = 12, grid: int = 7, spacing_km: float = 1.6) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    span = (grid - 1) * spacing_km
    rows = []
    # window templates (minutes since midnight): open, close, last_checkin
    templates = [(9*60, 11*60, 10*60+45), (10*60, 12*60, 11*60+30), (11*60, 13*60, 12*60+30),
                 (12*60, 13*60, 12*60+45), (16*60, 18*60, 17*60+30), (10*60, 12*60+30, 12*60)]
    for k in range(n):
        x, y = rng.uniform(0.2, span - 0.2, 2)
        o, c, l = templates[int(rng.integers(0, len(templates)))]
        lat, lon = to_latlon(x, y)
        rows.append({"pantry_id": f"P{k+1:02d}", "name": f"Synthetic Pantry {k+1}", "lat": lat, "lon": lon,
                     "open_min": o, "close_min": c, "last_checkin_min": l,
                     "walk_in": True, "verified": False, "source": "SYNTHETIC"})
    df = pd.DataFrame(rows)
    df[["open_min", "close_min", "last_checkin_min"]] = df[["open_min", "close_min", "last_checkin_min"]].astype(float)
    df.to_csv(path, index=False)
    return df
