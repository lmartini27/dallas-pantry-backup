"""Main analysis (baseline assumptions). With no arguments it generates and analyses SYNTHETIC demo data;
with --gtfs and --pantries it analyses real inputs."""
import sys, argparse
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from pantrynet import synth, gtfs, csa, analysis, plots

ap = argparse.ArgumentParser()
ap.add_argument("--gtfs", help="GTFS folder (default: generate synthetic)")
ap.add_argument("--pantries", help="pantries CSV (default: generate synthetic)")
ap.add_argument("--date", default="2026-12-02", help="service date YYYY-MM-DD")
args = ap.parse_args()

out = ROOT / "outputs"; out.mkdir(exist_ok=True)
synthetic = not (args.gtfs and args.pantries)
gdir = Path(args.gtfs) if args.gtfs else ROOT / "data" / "synthetic_gtfs"
pcsv = Path(args.pantries) if args.pantries else ROOT / "data" / "synthetic_pantries.csv"
if synthetic:
    synth.make_gtfs(gdir); synth.make_pantries(pcsv)
pantries = pd.read_csv(pcsv)
net = gtfs.load_gtfs(gdir, date.fromisoformat(args.date))
router = csa.Router(net, csa.Params())

sc = analysis.scenario_table(router, pantries)
cov = analysis.coverage(sc)
fix = analysis.smallest_fix(sc)
sens = analysis.shift_sensitivity(router, pantries)
sc.to_csv(out / "scenarios.csv", index=False); cov.to_csv(out / "coverage_by_origin.csv", index=False)
fix.to_csv(out / "smallest_fix.csv", index=False); sens.to_csv(out / "shift_sensitivity.csv", index=False)
plots.coverage_heatmap(sc, out / "fig1_backup_heatmap.png", synthetic)
plots.city_map(pantries, net.stops, cov, out / "fig2_coverage_map.png", synthetic)
plots.shift_chart(sens, out / "fig3_shift_sensitivity.png", synthetic)
plots.near_miss_chart(fix, out / "fig4_smallest_fix.png", synthetic)

print("scenarios:", len(sc), "| with backup:", f"{sc.backup.mean():.1%}", "| near-miss:", f"{sc.near_miss.mean():.1%}")
print(cov.round(2).to_string(index=False))
print("\nTop near-misses (no backup today):")
print(fix[~fix.already_has_backup].head(8).round(1).to_string(index=False))
best = sens.sort_values("connections_change", ascending=False).head(3)
print("\nBest window shifts for network coverage:"); print(best.round(3).to_string(index=False))
