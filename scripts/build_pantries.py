"""Build data/pantries.csv for ONE service weekday from data/pantry_hours.csv.

    python3 scripts/build_pantries.py --day Tue            # needs internet (Census geocoder) unless lat/lon are filled in
    python3 scripts/build_pantries.py --day Tue --assume-checkin-before-close 30

last_checkin: the published value if present; otherwise close time minus --assume-checkin-before-close
(default 0 = the closing time). Pantries with an assumed value are flagged in the 'checkin_assumed' column.
Geocoding results are cached in data/geocode_cache.csv. If the geocoder fails, fill lat/lon in pantry_hours.csv by hand.
"""
import argparse, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser()
ap.add_argument("--day", required=True, choices=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
ap.add_argument("--assume-checkin-before-close", type=float, default=0.0)
ap.add_argument("--hours", default=str(ROOT / "data" / "pantry_hours.csv"))
ap.add_argument("--out", default=str(ROOT / "data" / "pantries.csv"))
a = ap.parse_args()


def mins(s):
    if pd.isna(s) or str(s).strip() == "":
        return None
    h, m = str(s).split(":"); return int(h) * 60 + int(m)


cache_path = ROOT / "data" / "geocode_cache.csv"
cache = pd.read_csv(cache_path).set_index("address").to_dict("index") if cache_path.exists() else {}


def variants(addr):
    """Address spellings to try, most specific first."""
    import re
    base = re.sub(r"\s*\(.*?\)", "", addr)                       # drop "(guest entrance)"
    base = re.sub(r"\s+(Suite|Building|Ste|Bldg)\s+\w+", "", base, flags=re.I)
    out = [addr, base]
    long = (base.replace(" Dr,", " Drive,").replace(" St,", " Street,").replace(" Ln,", " Lane,")
            .replace(" Blvd,", " Boulevard,").replace(" Ave,", " Avenue,"))
    out += [long, re.sub(r",?\s*\d{5}$", "", base), re.sub(r",?\s*\d{5}$", "", long)]
    seen, res = set(), []
    for v in out:
        if v not in seen:
            seen.add(v); res.append(v)
    return res


def _census(addr):
    url = ("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?"
           + urllib.parse.urlencode({"address": addr, "benchmark": "Public_AR_Current", "format": "json"}))
    req = urllib.request.Request(url, headers={"User-Agent": "pantry-backup-research/0.1"})
    m = json.load(urllib.request.urlopen(req, timeout=30))["result"]["addressMatches"]
    return (m[0]["coordinates"]["y"], m[0]["coordinates"]["x"]) if m else None


def geocode(addr):
    if addr in cache:
        return cache[addr]["lat"], cache[addr]["lon"]
    for v in variants(addr):
        hit = _census(v)
        time.sleep(0.5)
        if hit:
            cache[addr] = {"lat": hit[0], "lon": hit[1]}
            pd.DataFrame([{"address": k, **val} for k, val in cache.items()]).to_csv(cache_path, index=False)
            return hit
    return None


df = pd.read_csv(a.hours, dtype=str).fillna("")
df = df[df["day"] == a.day].copy()
if df.empty:
    sys.exit(f"No pantries listed for {a.day}")
out, failed = [], []
for r in df.itertuples():
    hit = (float(r.lat), float(r.lon)) if r.lat and r.lon else geocode(r.address)
    if hit is None:
        failed.append(r)
        continue
    lat, lon = hit
    o, c, l = mins(r.open), mins(r.close), mins(r.last_checkin)
    assumed = l is None
    if assumed:
        l = c - a.assume_checkin_before_close
    out.append({"pantry_id": r.pantry_id, "name": r.name, "lat": lat, "lon": lon, "open_min": float(o),
                "close_min": float(c), "last_checkin_min": float(l), "checkin_assumed": assumed,
                "eligible_zips": r.eligible_zips or "ALL", "walk_in": True, "verified": False,
                "source": r.source_url, "notes": r.notes})
if failed:
    print("\nCould not geocode these (fill lat/lon by hand in data/pantry_hours.csv, e.g. from Google Maps:")
    print("right-click the spot -> click the coordinates to copy 'lat, lon'):")
    for r in failed:
        print(f"  {r.pantry_id}: {r.address}")
    sys.exit(1)
pd.DataFrame(out).to_csv(a.out, index=False)
pd.DataFrame([{"address": k, **v} for k, v in cache.items()]).to_csv(cache_path, index=False)
print(f"wrote {a.out}: {len(out)} pantries open on {a.day}")
print(pd.DataFrame(out)[["pantry_id", "open_min", "close_min", "last_checkin_min", "checkin_assumed"]].to_string(index=False))
