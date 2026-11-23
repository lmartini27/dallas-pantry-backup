"""Report figures from run_robust.py outputs.

    python3 scripts/run_robust.py ... --tag _close      # pantries.csv built with default (close-time) cutoffs
    python3 scripts/build_pantries.py --day Tue --assume-checkin-before-close 30
    python3 scripts/run_robust.py ... --tag _m30
    python3 scripts/make_report_figures.py --tags _close _m30 --labels "cutoff = closing time" "cutoff = close - 30 min"
"""
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--tags", nargs="+", required=True)
ap.add_argument("--labels", nargs="+")
ap.add_argument("--pantries", default=str(ROOT / "data" / "pantries.csv"))
ap.add_argument("--day", default="Tuesday")
ap.add_argument("--note", default="PRELIMINARY - scheduled service only; most last-check-in times are assumed, not published")
a = ap.parse_args()
labels = a.labels or a.tags
out = ROOT / "outputs"
P = pd.read_csv(a.pantries)


def hhmm(m): return f"{int(m)//60 % 24:02d}:{int(m)%60:02d}"


# Figure A: robust coverage per origin, one bar group per cutoff assumption
cov = {t: pd.read_csv(out / f"robust_coverage{t}.csv").set_index("origin") for t in a.tags}
origins = list(cov[a.tags[0]].index)
x = np.arange(len(origins)); w = 0.8 / len(a.tags)
fig, ax = plt.subplots(figsize=(9, 4.8))
for k, t in enumerate(a.tags):
    ax.bar(x + k * w, cov[t].loc[origins, "share_robust_backup"] * 100, w, label=labels[k])
ax.set_xticks(x + w * (len(a.tags) - 1) / 2, origins)
ax.set_ylabel("% of departure times with a backup\n(even for a slow walker)")
ax.set_title("Backup coverage by pantry (rider who leaves empty-handed)")
ax.set_ylim(0, 125); ax.legend(fontsize=8, loc="upper center", ncol=2)
fig.text(0.5, 0.01, a.note, ha="center", fontsize=7, color="#b00020")
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(out / "report_fig1_coverage_by_pantry.png", dpi=170); plt.close(fig)

# Figure B: pantry windows (timeline) shaded by robust coverage under the LAST tag
last = cov[a.tags[-1]]
fig, ax = plt.subplots(figsize=(9, 4.8))
cm = plt.get_cmap("RdYlGn")
order = P.sort_values("open_min").reset_index(drop=True)
for i, r in order.iterrows():
    c = last.loc[r.pantry_id, "share_robust_backup"] if r.pantry_id in last.index else 0
    ax.barh(i, r.close_min - r.open_min, left=r.open_min, color=cm(c), edgecolor="k")
    ax.plot([r.last_checkin_min] * 2, [i - 0.4, i + 0.4], color="k", lw=2)
    ax.text(r.open_min + 3, i, f"{r.pantry_id}  {int(round(c*100))}%", va="center", fontsize=8)
ax.set_yticks([]); ax.invert_yaxis()
lo, hi = order.open_min.min() - 30, order.close_min.max() + 30
ticks = np.arange(int(lo // 60) * 60, hi + 1, 60)
ax.set_xticks(ticks, [hhmm(t) for t in ticks]); ax.set_xlim(lo, hi)
ax.set_title(f"{a.day} service windows, colored by backup coverage ({labels[-1]})\nblack tick = last check-in used")
sm = plt.cm.ScalarMappable(cmap=cm, norm=plt.Normalize(0, 100)); fig.colorbar(sm, ax=ax, label="% departure times with a robust backup")
fig.text(0.5, 0.01, a.note, ha="center", fontsize=7, color="#b00020")
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(out / "report_fig2_windows_and_coverage.png", dpi=170); plt.close(fig)
print("wrote report_fig1_coverage_by_pantry.png and report_fig2_windows_and_coverage.png in outputs/")
