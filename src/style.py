"""Series style loader — registers the bundled Inter fonts and applies the shared matplotlib style.

Usage (from repo root):
    from src.style import use_series_style
    use_series_style()
    use_series_style(dark=True)   # the dark twin

Falls back to matplotlib defaults (DejaVu) if font files are missing — charts still render.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def use_series_style(dark: bool = False):
    """Apply the Six-on-SG style — light by default, `dark=True` for the dark twin. Safe to call more than once."""
    for ttf in ("Inter-Regular.ttf", "Inter-SemiBold.ttf"):
        f = ASSETS / "fonts" / ttf
        if f.exists():
            font_manager.fontManager.addfont(str(f))
    plt.style.use(str(ASSETS / ("style-dark.mplstyle" if dark else "style.mplstyle")))
