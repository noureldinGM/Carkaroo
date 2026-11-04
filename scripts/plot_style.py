"""Shared matplotlib style for the report charts: the Carkaroo look (light mode, static PNG)."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Carkaroo colors (design/tokens.css): charts sit on the paper background,
# our AI is always chassis green, baselines get the other kit colors or grey.
SURFACE = "#f5f3ec"        # paper
TEXT = "#1c1d1a"           # ink
TEXT_2 = "#545750"         # ink-2
GRID = "#e4e2d8"           # line
MUTED = "#b9b8b2"          # bars that are not the focus
SERIES = ["#1a7f45", "#2f6fd0", "#c4570f", "#6b6e66", "#e2483d", "#23231f"]  # chassis, sonar, wire orange, grey, wire red, tire
ML = SERIES[0]
MATERIAL = {"A": "#3566a8", "B": "#1d7a6c", "C": "#b35a1f"}

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT_2,
    "axes.titlecolor": TEXT,
    "axes.titlesize": 13,
    "axes.titleweight": "normal",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": TEXT_2,
    "ytick.color": TEXT_2,
    "font.size": 10,
    "legend.frameon": False,
    "lines.linewidth": 2,
    "font.family": "sans-serif",
    "font.sans-serif": ["IBM Plex Sans", "Segoe UI", "DejaVu Sans"],
})


def finish(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
