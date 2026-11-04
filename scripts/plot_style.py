"""Shared matplotlib style for the report charts: the Carkaroo Night Race look (light mode, static PNG)."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Carkaroo "Night Race" colors (design/tokens.css): white charts that sit inside the poster's
# white panels. Our AI is always asphalt black; the other methods are chrome, gold and red (worst).
SURFACE = "#ffffff"        # card
TEXT = "#121314"           # ink
TEXT_2 = "#4a4e53"         # ink-2
GRID = "#e2e4e6"           # primary-soft
MUTED = "#c9cdd1"          # chrome-light: bars that are not the focus
SERIES = ["#121314", "#8b9096", "#c99a12", "#b7372a", "#3566a8", "#63686e"]  # asphalt, chrome, gold, red, steel, grey
ML = SERIES[0]
SIGNAL = "#f6c21c"         # the one accent: highlight bands, never thin lines on white
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
    "lines.solid_capstyle": "round",
})


def finish(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
