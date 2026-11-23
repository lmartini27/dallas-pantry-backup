"""Earliest-arrival search (Connection Scan) with walking access/egress, transfers and
short walking transfers between nearby stops (e.g. opposite corners, bus bay <-> rail platform).

Trip-aware: staying on the same trip needs no transfer buffer; changing trips at the same stop
needs `transfer_min`; walking to a nearby stop costs the walking time plus `foot_buffer_min`.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .gtfs import Network, haversine_km

INF = float("inf")


@dataclass
class Params:
    walk_kmh: float = 4.8          # slow-ish adult walking speed
    detour: float = 1.25           # street-network detour vs straight line
    max_walk_km: float = 1.0       # max straight-line walk to/from a stop (~15 min after detour)
    transfer_min: float = 4.0      # buffer when changing trips at the same stop
    footpath_km: float = 0.4       # walking transfers between stops up to this far apart
    foot_buffer_min: float = 1.0   # extra margin after a walking transfer
    checkin_buffer_min: float = 0  # extra margin required before last check-in
    max_wait_min: float = 30.0     # longest a rider will wait outside a pantry before it opens
    horizon_min: float = 240.0     # stop scanning connections this long after departure


def walk_minutes(km: float, p: Params) -> float:
    return km * p.detour / p.walk_kmh * 60.0


class Router:
    def __init__(self, net: Network, params: Params | None = None):
        self.net = net
        self.p = params or Params()
        self.stop_ids = list(net.stops["stop_id"])
        self.idx = {s: i for i, s in enumerate(self.stop_ids)}
        c = net.connections
        self.c_dep_stop = c["dep_stop"].map(self.idx).to_numpy()
        self.c_arr_stop = c["arr_stop"].map(self.idx).to_numpy()
        self.c_dep = c["dep"].to_numpy(float)
        self.c_arr = c["arr"].to_numpy(float)
        self.c_trip = c["trip_id"].to_numpy()
        self.c_route = c["route"].to_numpy() if "route" in c.columns else self.c_trip
        self.stop_name = net.stops["stop_name"].to_numpy() if "stop_name" in net.stops.columns else np.array(self.stop_ids)
        self.lat = net.stops["stop_lat"].to_numpy(float)
        self.lon = net.stops["stop_lon"].to_numpy(float)
        self._access_cache: dict[tuple[float, float], list[tuple[int, float]]] = {}
        self._arr_cache: dict[tuple[float, float, float], np.ndarray] = {}
        self.near = self._build_footpaths()

    def _build_footpaths(self) -> list[list[tuple[int, float]]]:
        """For each stop: [(other stop, walk minutes)] within footpath_km (grid-hash, no scipy needed)."""
        r = self.p.footpath_km
        out: list[list[tuple[int, float]]] = [[] for _ in self.lat]
        if r <= 0:
            return out
        dlat = r / 111.0
        dlon = r / (111.0 * np.cos(np.radians(self.lat.mean())))
        cells: dict[tuple[int, int], list[int]] = {}
        for i in range(len(self.lat)):
            cells.setdefault((int(self.lat[i] // dlat), int(self.lon[i] // dlon)), []).append(i)
        for i in range(len(self.lat)):
            ci, cj = int(self.lat[i] // dlat), int(self.lon[i] // dlon)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for j in cells.get((ci + di, cj + dj), ()):
                        if j != i:
                            d = haversine_km(self.lat[i], self.lon[i], self.lat[j], self.lon[j])
                            if d <= r:
                                out[i].append((j, walk_minutes(d, self.p) + self.p.foot_buffer_min))
        return out

    def access(self, lat: float, lon: float) -> list[tuple[int, float]]:
        """(stop index, walk minutes) for stops within max_walk_km."""
        key = (round(lat, 6), round(lon, 6))
        if key not in self._access_cache:
            out = []
            for i in range(len(self.lat)):
                d = haversine_km(lat, lon, self.lat[i], self.lon[i])
                if d <= self.p.max_walk_km:
                    out.append((i, walk_minutes(d, self.p)))
            self._access_cache[key] = out
        return self._access_cache[key]

    def earliest_arrivals(self, lat: float, lon: float, depart: float) -> np.ndarray:
        """Earliest time each stop can be reached when leaving (lat, lon) at `depart` (memoized)."""
        key = (round(lat, 6), round(lon, 6), float(depart))
        hit = self._arr_cache.get(key)
        if hit is None:
            hit = self._scan(lat, lon, depart)[0]
            self._arr_cache[key] = hit
        return hit

    def _scan(self, lat: float, lon: float, depart: float, track: bool = False):
        n = len(self.stop_ids)
        walk = np.full(n, INF)      # reached on foot from the origin
        transit = np.full(n, INF)   # reached by vehicle (same-stop transfer needs transfer_min)
        foot = np.full(n, INF)      # reached by vehicle then a short walk from a nearby stop
        arr_conn = np.full(n, -1)   # (tracking) connection that delivered the best vehicle arrival
        foot_src = np.full(n, -1)   # (tracking) connection that delivered the walking transfer
        for i, w in self.access(lat, lon):
            walk[i] = depart + w
        board: dict = {}            # trip -> (boarding connection, previous connection, via)
        boarded: set = set()
        tb = self.p.transfer_min
        start = np.searchsorted(self.c_dep, depart, side="left")
        stop_at = depart + self.p.horizon_min
        for k in range(start, len(self.c_dep)):
            d = self.c_dep[k]
            if d > stop_at:
                break
            t = self.c_trip[k]
            ds = self.c_dep_stop[k]
            if t not in boarded:
                if walk[ds] <= d:
                    via, prev = "origin", -1
                elif transit[ds] + tb <= d:
                    via, prev = "same", arr_conn[ds]
                elif foot[ds] <= d:
                    via, prev = "foot", foot_src[ds]
                else:
                    continue
                boarded.add(t)
                if track:
                    board[t] = (k, int(prev), via)
            a = self.c_arr_stop[k]
            arr = self.c_arr[k]
            if arr < transit[a]:
                transit[a] = arr
                arr_conn[a] = k
            for j, w in self.near[a]:
                if arr + w < foot[j]:
                    foot[j] = arr + w
                    foot_src[j] = k
        res = np.minimum(walk, transit)
        return res, (transit, arr_conn, board, foot, foot_src)

    def arrival_at(self, origin: tuple[float, float], depart: float, dest: tuple[float, float]) -> float:
        """Earliest arrival at dest (door to door); direct walking allowed."""
        d = haversine_km(*origin, *dest)
        best = depart + walk_minutes(d, self.p) if d <= self.p.max_walk_km * 1.6 else INF
        arr = self.earliest_arrivals(origin[0], origin[1], depart)
        for i, w in self.access(*dest):
            if arr[i] < INF:
                best = min(best, arr[i] + w)
        return best

    def explain(self, origin: tuple[float, float], depart: float, dest: tuple[float, float]) -> dict:
        """Best door-to-door itinerary (routes, stops, walks, times) for checking against a trip planner."""
        _, (transit, arr_conn, board, foot, foot_src) = self._scan(origin[0], origin[1], depart, track=True)
        dkm = haversine_km(*origin, *dest)
        best = depart + walk_minutes(dkm, self.p) if dkm <= self.p.max_walk_km * 1.6 else INF
        best_stop, egress = None, 0.0
        for i, w in self.access(*dest):
            if transit[i] < INF and transit[i] + w < best:
                best, best_stop, egress = transit[i] + w, i, w
        if best == INF:
            return {"arrive": INF, "legs": [], "note": "no itinerary found within horizon"}
        if best_stop is None:
            return {"arrive": best, "legs": [], "note": "walk directly"}
        legs, k = [], int(arr_conn[best_stop])
        access_walk = float("nan")
        while k != -1:
            bk, prev, via = board[self.c_trip[k]]
            leg = {"route": str(self.c_route[k]), "board": str(self.stop_name[self.c_dep_stop[bk]]),
                   "board_time": float(self.c_dep[bk]), "alight": str(self.stop_name[self.c_arr_stop[k]]),
                   "alight_time": float(self.c_arr[k]), "transfer": via}
            if via == "foot" and prev != -1:
                a_stop, b_stop = self.c_arr_stop[prev], self.c_dep_stop[bk]
                leg["transfer_walk_min"] = walk_minutes(haversine_km(self.lat[a_stop], self.lon[a_stop], self.lat[b_stop], self.lon[b_stop]), self.p)
            if via == "origin":
                access_walk = next((w for i, w in self.access(*origin) if i == self.c_dep_stop[bk]), float("nan"))
            legs.append(leg)
            k = prev
        legs.reverse()
        return {"arrive": best, "legs": legs, "access_walk_min": access_walk, "egress_walk_min": egress}
