"""Download DART's official GTFS (run on YOUR computer) and sanity-check it.

    python3 scripts/fetch_and_check_dart.py --date 2026-12-02
"""
import argparse, io, sys, urllib.request, zipfile
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from pantrynet import gtfs

URL = "https://www.dart.org/transitdata/latest/google_transit.zip"  # producer URL listed on Mobility Database
ap = argparse.ArgumentParser()
ap.add_argument("--url", default=URL)
ap.add_argument("--date", default="2026-12-02")
ap.add_argument("--out", default=str(ROOT / "data" / "dart_gtfs"))
a = ap.parse_args()

out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
req = urllib.request.Request(a.url, headers={"User-Agent": "pantry-backup-research/0.1 (student project)"})
data = urllib.request.urlopen(req, timeout=60).read()
zipfile.ZipFile(io.BytesIO(data)).extractall(out)
print("saved to", out, "| files:", sorted(p.name for p in out.iterdir()))

fi = out / "feed_info.txt"
if fi.exists():
    f = pd.read_csv(fi, dtype=str); print(f.T.to_string(header=False))
d = date.fromisoformat(a.date)
svc = gtfs.active_services(out, d)
print(f"\nservice ids active on {d} ({d:%A}):", len(svc))
net = gtfs.load_gtfs(out, d)
c = net.connections
print("stops:", len(net.stops), "| connections:", len(c))
if len(c):
    print("first dep %.0f min (%s) | last dep %.0f min" % (c.dep.min(), f"{int(c.dep.min())//60:02d}:{int(c.dep.min())%60:02d}", c.dep.max()))
    mid = c[(c.dep >= 600) & (c.dep < 780)]
    print("connections 10:00-13:00:", len(mid))
else:
    print("NO SERVICE FOUND for that date: check the feed's service date range (feed_info.txt / calendar.txt).")
