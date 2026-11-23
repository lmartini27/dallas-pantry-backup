"""Print the model's itinerary for one pair so you can compare it with DART's trip planner.

    python3 scripts/explain_trip.py --gtfs data/dart_gtfs --pantries data/pantries.csv --date 2026-12-01 --from IVCC --to PGFP --best
    python3 scripts/explain_trip.py ... --from STEW --to MOC --depart 12:15
--best searches the origin's open window (5-min steps) for the departure with the most slack.
"""
import argparse, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from pantrynet import gtfs, csa

ap = argparse.ArgumentParser()
ap.add_argument("--gtfs", default=str(ROOT / "data" / "dart_gtfs"))
ap.add_argument("--pantries", default=str(ROOT / "data" / "pantries.csv"))
ap.add_argument("--date", default="2026-12-01")
ap.add_argument("--from", dest="src", required=True)
ap.add_argument("--to", dest="dst", required=True)
ap.add_argument("--depart", help="HH:MM")
ap.add_argument("--best", action="store_true")
ap.add_argument("--walk-kmh", type=float, default=None)
ap.add_argument("--detour", type=float, default=None)
ap.add_argument("--max-walk-km", type=float, default=None)
ap.add_argument("--foot-buffer", type=float, default=None)
a = ap.parse_args()


def hm(m): return f"{int(m)//60:02d}:{int(round(m))%60:02d}" if m < 1e8 else "never"


P = pd.read_csv(a.pantries).set_index("pantry_id")
A, B = P.loc[a.src], P.loc[a.dst]
pk = {k: v for k, v in dict(walk_kmh=a.walk_kmh, detour=a.detour, max_walk_km=a.max_walk_km,
                            foot_buffer_min=a.foot_buffer).items() if v is not None}
r = csa.Router(gtfs.load_gtfs(a.gtfs, date.fromisoformat(a.date)), csa.Params(**pk))
o, d = (A.lat, A.lon), (B.lat, B.lon)

if a.best:
    cands = []
    t = A.open_min
    while t < A.close_min:
        ex = r.explain(o, t, d); cands.append((B.last_checkin_min - ex["arrive"], t, ex)); t += 5
    slack, t, ex = max(cands, key=lambda x: x[0])
else:
    h, m = a.depart.split(":"); t = int(h) * 60 + int(m)
    ex = r.explain(o, t, d); slack = B.last_checkin_min - ex["arrive"]

print(f"{a.src} -> {a.dst} on {a.date}: leave {hm(t)}")
if ex["legs"]:
    print(f"  walk to first stop: {ex['access_walk_min']:.0f} min")
    for L in ex["legs"]:
        if L.get("transfer") == "foot":
            print(f"  (walk ~{L['transfer_walk_min']:.0f} min to the next stop)")
        print(f"  ride {L['route']}: {L['board']} {hm(L['board_time'])}  ->  {L['alight']} {hm(L['alight_time'])}")
    print(f"  walk to pantry: {ex['egress_walk_min']:.0f} min")
else:
    print("  ", ex.get("note"))
print(f"  ARRIVE {hm(ex['arrive'])} | {a.dst} opens {hm(B.open_min)}, last check-in {hm(B.last_checkin_min)}"
      f"{' (ASSUMED)' if B.get('checkin_assumed') else ''} | slack {slack:+.0f} min")
