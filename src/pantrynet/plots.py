from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SYN = "SYNTHETIC DATA - NOT REAL PANTRIES OR DART SERVICE"


def _stamp(ax_or_fig, synthetic: bool):
    if synthetic:
        fig = ax_or_fig.figure if hasattr(ax_or_fig, "figure") else ax_or_fig
        fig.text(0.5, 0.012, SYN, ha="center", va="bottom", fontsize=8, color="#b00020", weight="bold")


def hhmm(m): return f"{int(m)//60:02d}:{int(m)%60:02d}"


def coverage_heatmap(sc: pd.DataFrame, out, synthetic=True):
    g = sc.groupby(["origin", "depart"])["backup"].sum().unstack("depart").fillna(0)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    im = ax.imshow(g.to_numpy(), aspect="auto", cmap="viridis")
    ax.set_yticks(range(len(g.index)), g.index)
    cols = list(g.columns)
    tick = list(range(0, len(cols), 4))
    ax.set_xticks(tick, [hhmm(cols[i]) for i in tick])
    ax.set_xlabel("Time leaving origin pantry"); ax.set_ylabel("Origin pantry")
    ax.set_title("Reachable backup pantries by departure time")
    fig.colorbar(im, ax=ax, label="# backups reachable before last check-in")
    fig.tight_layout(rect=(0, 0.03, 1, 1)); _stamp(fig, synthetic)
    fig.savefig(out, dpi=160); plt.close(fig)


def shift_chart(sens: pd.DataFrame, out, synthetic=True):
    pv = sens.pivot(index="pantry", columns="shift_min", values="connections_change")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    im = ax.imshow(pv.to_numpy(), aspect="auto", cmap="RdBu", vmin=-abs(pv.to_numpy()).max(), vmax=abs(pv.to_numpy()).max())
    ax.set_xticks(range(len(pv.columns)), [f"{c:+d}" for c in pv.columns])
    ax.set_yticks(range(len(pv.index)), pv.index)
    ax.set_xlabel("Shift this pantry's window (min, same total hours)"); ax.set_ylabel("Pantry shifted")
    ax.set_title("Net change in feasible backup connections (all origins, 15-min grid)")
    fig.colorbar(im, ax=ax); fig.tight_layout(rect=(0, 0.03, 1, 1)); _stamp(fig, synthetic)
    fig.savefig(out, dpi=160); plt.close(fig)


def near_miss_chart(fix: pd.DataFrame, out, synthetic=True):
    f = fix[~fix.already_has_backup].head(12)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    labels = [f"{o}->{d}" for o, d in zip(f.origin, f.dest)]
    ax.barh(labels[::-1], f.min_extension_min.to_numpy()[::-1], color="#1f6f8b")
    ax.set_xlabel("Minutes of extra check-in time needed at destination")
    ax.set_title("Smallest change that creates a backup (pairs with none today)")
    fig.tight_layout(rect=(0, 0.03, 1, 1)); _stamp(fig, synthetic)
    fig.savefig(out, dpi=160); plt.close(fig)


def city_map(pantries: pd.DataFrame, stops: pd.DataFrame, cov: pd.DataFrame, out, synthetic=True):
    m = pantries.merge(cov, left_on="pantry_id", right_on="origin")
    fig, ax = plt.subplots(figsize=(6.5, 6.2))
    ax.scatter(stops.stop_lon, stops.stop_lat, s=6, c="#bbbbbb", label="transit stops")
    sc = ax.scatter(m.lon, m.lat, s=140, c=m.share_with_backup * 100, cmap="RdYlGn", vmin=0, vmax=100,
                    edgecolor="k", zorder=3)
    for r in m.itertuples():
        ax.annotate(r.pantry_id, (r.lon, r.lat), xytext=(4, 4), textcoords="offset points", fontsize=8)
    fig.colorbar(sc, ax=ax, label="% of departure times with >=1 backup")
    ax.set_title("Backup coverage by origin pantry"); ax.set_xticks([]); ax.set_yticks([])
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); _stamp(fig, synthetic)
    fig.savefig(out, dpi=160); plt.close(fig)
