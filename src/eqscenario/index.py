"""Weighted building-damage index and its sensitivity to the weights."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .data import DAMAGE_COLS

# Weights per damage level, in the order very heavy, heavy, moderate, light.
# Analyst-chosen severity weights: large contributions from very heavy and
# heavy damage, smaller ones from moderate and light damage. This is a ranking
# proxy, not an official IMM scale or a calibrated replacement-cost estimate.
WEIGHT_SCHEMES = {
    "severity weights (main)": (1.00, 0.50, 0.10, 0.02),
    "linear 4-3-2-1": (4.0, 3.0, 2.0, 1.0),
    "equal (count)": (1.0, 1.0, 1.0, 1.0),
    "steep 1-0.25-0.05-0.01": (1.00, 0.25, 0.05, 0.01),
    "collapse only": (1.0, 0.0, 0.0, 0.0),
}
MAIN_SCHEME = "severity weights (main)"


def damage_index(df: pd.DataFrame, weights=WEIGHT_SCHEMES[MAIN_SCHEME]) -> np.ndarray:
    return df[DAMAGE_COLS].to_numpy(dtype=float) @ np.asarray(weights, dtype=float)


def add_index(df: pd.DataFrame) -> pd.DataFrame:
    """Add the main index, a size-free severity score and ranks."""
    out = df.copy()
    out["damage_index"] = damage_index(out)
    # Mean damage ratio of the damaged buildings: how severe, not how many.
    out["severity"] = out["damage_index"] / out["damaged_buildings"].where(
        out["damaged_buildings"] > 0
    )
    out["rank"] = out["damage_index"].rank(ascending=False, method="min").astype(int)
    return out


def sensitivity(df: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """Compare rankings under each weight scheme with the main scheme."""
    base = damage_index(df)
    base_top = set(np.argsort(-base)[:top_n])
    cas = df["deaths_serious"].to_numpy()
    rows = []
    for name, w in WEIGHT_SCHEMES.items():
        idx = damage_index(df, w)
        top = set(np.argsort(-idx)[:top_n])
        rows.append(
            {
                "scheme": name,
                "weights (vh, h, m, l)": ", ".join(f"{x:g}" for x in w),
                "spearman_vs_main": spearmanr(base, idx).statistic,
                f"top{top_n}_overlap_with_main": len(base_top & top) / top_n,
                "spearman_vs_deaths_serious": spearmanr(cas, idx).statistic,
            }
        )
    return pd.DataFrame(rows)


def district_index(nb: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "damage_index",
        "damaged_buildings",
        "deaths_serious",
        "can_kaybi_sayisi",
        "gecici_barinma",
    ]
    out = nb.groupby("district", as_index=False)[cols].sum()
    out["severity"] = out["damage_index"] / out["damaged_buildings"]
    out["rank"] = out["damage_index"].rank(ascending=False, method="min").astype(int)
    return out.sort_values("rank").reset_index(drop=True)
