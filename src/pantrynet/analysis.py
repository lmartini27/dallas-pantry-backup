"""Backup analysis: who can reach a second pantry before its last check-in?

Scenario = rider leaves origin pantry A at time t (grid across A's open window).
A backup exists at B if earliest arrival <= B.last_checkin - buffer and B is not closed.
Near miss = arrival is after B.last_checkin by <= miss_limit minutes.
"""
from __future__ import annotations
from dataclasses import replace
import numpy as np
import pandas as pd
from .csa import Router, INF


def zips(v) -> set:
    v = "ALL" if v is None or (isinstance(v, float) and v != v) else str(v)
    return {z.strip() for z in v.split(";") if z.strip()}


def eligible_overlap(a, b) -> bool:
    """True if some resident could be served by both pantries (ALL = no stated ZIP rule)."""
    za, zb = zips(getattr(a, "eligible_zips", "ALL")), zips(getattr(b, "eligible_zips", "ALL"))
    return "ALL" in za or "ALL" in zb or bool(za & zb)


def departure_grid(row, step: int = 15) -> list[float]:
    return list(np.arange(row.open_min, row.close_min, step, dtype=float))


def scenario_table(router: Router, pantries: pd.DataFrame, step: int = 15, miss_limit: float = 60.0) -> pd.DataFrame:
    recs = []
    for a in pantries.itertuples():
        for t in departure_grid(a, step):
            arr = router.earliest_arrivals(a.lat, a.lon, t)
            for b in pantries.itertuples():
                if b.pantry_id == a.pantry_id:
                    continue
                best = INF
                for i, w in router.access(b.lat, b.lon):
                    if arr[i] < INF:
                        best = min(best, arr[i] + w)
                slack = (b.last_checkin_min - router.p.checkin_buffer_min) - best if best < INF else -INF
                ok = eligible_overlap(a, b)
                wait = (b.open_min - best) if best < INF else INF      # minutes early, if any
                too_early = bool(wait > router.p.max_wait_min)           # would have to wait too long outside
                feasible = bool(slack >= 0 and not too_early)
                recs.append({"origin": a.pantry_id, "dest": b.pantry_id, "depart": t, "arrive": best,
                             "slack_min": slack, "too_early": too_early, "transit_ok": feasible,
                             "eligible_overlap": ok, "backup": bool(feasible and ok),
                             "near_miss": bool(ok and -miss_limit <= slack < 0)})
    return pd.DataFrame(recs)


def coverage(sc: pd.DataFrame) -> pd.DataFrame:
    """Per origin: share of departure times with >=1 backup, and mean backups."""
    g = sc.groupby(["origin", "depart"])["backup"].sum().reset_index()
    return g.groupby("origin").agg(share_with_backup=("backup", lambda s: float((s > 0).mean())),
                                   mean_backups=("backup", "mean")).reset_index()


def shift_window(pantries: pd.DataFrame, pid: str, minutes: float) -> pd.DataFrame:
    """Shift one pantry's whole window; total hours stay fixed."""
    p = pantries.copy()
    cols = ["open_min", "close_min", "last_checkin_min"]
    p[cols] = p[cols].astype(float)
    m = p["pantry_id"] == pid
    for col in ("open_min", "close_min", "last_checkin_min"):
        p.loc[m, col] = p.loc[m, col] + minutes
    return p


def shift_sensitivity(router: Router, pantries: pd.DataFrame, shifts=(-60, -30, -15, 15, 30, 60),
                      step: int = 15) -> pd.DataFrame:
    base = scenario_table(router, pantries, step)
    base_cov = coverage(base).set_index("origin")["share_with_backup"]
    base_ok = set(map(tuple, base.loc[base.backup, ["origin", "dest", "depart"]].to_numpy()))
    rows = []
    for pid in pantries["pantry_id"]:
        for s in shifts:
            alt = scenario_table(router, shift_window(pantries, pid, s), step)
            ok = set(map(tuple, alt.loc[alt.backup, ["origin", "dest", "depart"]].to_numpy()))
            # P as destination: keys are stable for origins != P
            inb_base = {k for k in base_ok if k[1] == pid and k[0] != pid}
            inb_alt = {k for k in ok if k[1] == pid and k[0] != pid}
            cov = coverage(alt).set_index("origin")["share_with_backup"]
            rows.append({"pantry": pid, "shift_min": s,
                         "inbound_gained": len(inb_alt - inb_base), "inbound_lost": len(inb_base - inb_alt),
                         "own_riders_coverage_change": float(cov[pid] - base_cov[pid]),
                         "network_coverage_change": float(cov.mean() - base_cov.mean()),
                         "connections_change": int(alt.backup.sum() - base.backup.sum())})
    return pd.DataFrame(rows)


def smallest_fix(sc: pd.DataFrame, max_extension: float = 60.0) -> pd.DataFrame:
    """For each (origin, dest): smallest extension of dest's last check-in that creates a
    backup for at least one departure time, i.e. the 'threshold' an organizer can act on."""
    miss = sc[(sc.slack_min < 0) & (sc.slack_min >= -max_extension) & sc.eligible_overlap]
    out = (miss.groupby(["origin", "dest"])
           .agg(min_extension_min=("slack_min", lambda s: float(-s.max())),
                departures_fixed=("depart", "count")).reset_index())
    already = sc.groupby(["origin", "dest"])["backup"].any()
    out["already_has_backup"] = [bool(already[(o, d)]) for o, d in zip(out.origin, out.dest)]
    return out.sort_values("min_extension_min").reset_index(drop=True)
