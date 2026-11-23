"""Bracket the answer with optimistic / baseline / pessimistic rider assumptions.

A route-planner can differ from this model by a few minutes (walking speed, transfer buffers), and a
minute can flip whether a rider catches a bus. So each (origin, destination, departure) is classified:
  ROBUST    feasible even under pessimistic assumptions (slow walker, short max walk, longer buffers)
  POSSIBLE  feasible only under baseline/optimistic assumptions
  NO        infeasible even under optimistic assumptions
A 'definite near-miss' is NO under optimistic assumptions but within --miss minutes of the cutoff.

    python3 scripts/run_robust.py --gtfs data/dart_gtfs --pantries data/pantries.csv --date 2026-12-01
"""
import argparse, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from pantrynet import gtfs, csa, analysis

ap = argparse.ArgumentParser()
ap.add_argument("--gtfs", default=str(ROOT / "data" / "dart_gtfs"))
ap.add_argument("--pantries", default=str(ROOT / "data" / "pantries.csv"))
ap.add_argument("--date", default="2026-12-01")
ap.add_argument("--miss", type=float, default=30.0)
ap.add_argument("--tag", default="", help="suffix for output files, e.g. _close or _m30")
a = ap.parse_args()

SETS = {
    "optimistic": csa.Params(walk_kmh=5.5, detour=1.15, max_walk_km=1.2, transfer_min=3, foot_buffer_min=0.5),
    "baseline": csa.Params(),
    "pessimistic": csa.Params(walk_kmh=3.6, detour=1.35, max_walk_km=0.6, transfer_min=5, foot_buffer_min=2.0),
}
P = pd.read_csv(a.pantries)
net = gtfs.load_gtfs(a.gtfs, date.fromisoformat(a.date))
tabs = {}
for name, prm in SETS.items():
    print("running", name, "...", flush=True)
    t = analysis.scenario_table(csa.Router(net, prm), P, miss_limit=a.miss)
    tabs[name] = t.set_index(["origin", "dest", "depart"])

key = tabs["baseline"].index
df = pd.DataFrame(index=key)
for name in SETS:
    t = tabs[name].reindex(key)
    df[f"backup_{name}"] = t["backup"]
    df[f"slack_{name}"] = t["slack_min"]
df["eligible_overlap"] = tabs["baseline"]["eligible_overlap"]
df["class"] = "NO"
df.loc[df.backup_optimistic | df.backup_baseline, "class"] = "POSSIBLE"
df.loc[df.backup_pessimistic, "class"] = "ROBUST"
df["definite_near_miss"] = (~df.backup_optimistic) & df.eligible_overlap & (df.slack_optimistic < 0) & (df.slack_optimistic >= -a.miss)
df.reset_index().to_csv(ROOT / "outputs" / f"robust_scenarios{a.tag}.csv", index=False)

g = df.reset_index().groupby(["origin", "depart"])
per_dep = g.agg(robust=("class", lambda s: (s == "ROBUST").sum()), possible=("class", lambda s: (s != "NO").sum())).reset_index()
cov = per_dep.groupby("origin").agg(share_robust_backup=("robust", lambda s: (s > 0).mean()),
                                    share_possible_backup=("possible", lambda s: (s > 0).mean())).reset_index()
print("\nShare of departure times with >=1 backup (ROBUST = even under pessimistic assumptions):")
print(cov.round(2).to_string(index=False))

pairs = df.reset_index().groupby(["origin", "dest"]).agg(
    robust=("class", lambda s: (s == "ROBUST").any()), possible=("class", lambda s: (s != "NO").any()),
    best_slack_optimistic=("slack_optimistic", "max"), n_definite_near_miss=("definite_near_miss", "sum")).reset_index()
dn = pairs[(~pairs.possible) & (pairs.n_definite_near_miss > 0)].sort_values("best_slack_optimistic", ascending=False)
print(f"\nDEFINITE near-misses (miss the cutoff even under optimistic assumptions, within {a.miss:.0f} min):")
print(dn.round(1).to_string(index=False) if len(dn) else "  none")
fragile = pairs[pairs.possible & ~pairs.robust]
print("\nFRAGILE pairs (work only if the rider walks fast / connections are tight):")
print(f"  {len(fragile)} pairs (full list in the robust_pairs CSV in outputs/)")
print(fragile[["origin", "dest"]].head(25).to_string(index=False) if len(fragile) else "  none")
cov.to_csv(ROOT / "outputs" / f"robust_coverage{a.tag}.csv", index=False)
pairs.to_csv(ROOT / "outputs" / f"robust_pairs{a.tag}.csv", index=False)
