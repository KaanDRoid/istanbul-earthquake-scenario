"""Pipeline damage and temporary shelter need in the scenario table.

Column meanings follow the IMM data dictionary and the IMM / Boğaziçi
University KOERI loss estimation project (2019) that produced the table:

- dogalgaz_boru_hasari, icme_suyu_boru_hasari, atik_su_boru_hasari: estimated
  number of repair points ("onarım ihtiyacı duyulan nokta sayısı") in the
  natural gas, drinking water and wastewater pipe networks. The project report
  describes these as sums of repair needs computed per grid cell, not counts of
  individual leaks or breaks.
- gecici_barinma: temporary shelter need in households ("hane sayısı"), derived
  from the households living in residential buildings with moderate, heavy or
  very heavy damage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

UTILITY_COLS = [
    "dogalgaz_boru_hasari",
    "icme_suyu_boru_hasari",
    "atik_su_boru_hasari",
]
UTILITY_LABELS = {
    "dogalgaz_boru_hasari": "natural gas",
    "icme_suyu_boru_hasari": "drinking water",
    "atik_su_boru_hasari": "wastewater",
}
OTHER_COLS = ["gecici_barinma", "hastanede_tedavi_sayisi", "hafif_yarali_sayisi"]
COLUMN_NOTES = {
    "dogalgaz_boru_hasari": "natural gas pipe repair points",
    "icme_suyu_boru_hasari": "drinking water pipe repair points",
    "atik_su_boru_hasari": "wastewater pipe repair points",
    "gecici_barinma": "temporary shelter need (households)",
    "hastanede_tedavi_sayisi": "injured needing hospital treatment",
    "hafif_yarali_sayisi": "lightly injured",
}


def describe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Type, zeros and distribution of each previously unused column."""
    rows = []
    for col in UTILITY_COLS + OTHER_COLS:
        s = df[col]
        rows.append(
            {
                "column": col,
                "meaning": COLUMN_NOTES[col],
                "all_integer": bool((s == s.round()).all()),
                "zero_share": (s == 0).mean(),
                "mean": s.mean(),
                "median": s.median(),
                "p90": s.quantile(0.9),
                "max": s.max(),
                "city_total": s.sum(),
                "top10pct_share_of_total": s.nlargest(int(np.ceil(len(s) * 0.1))).sum()
                / s.sum(),
            }
        )
    return pd.DataFrame(rows)


def value_counts_table(df: pd.DataFrame) -> pd.DataFrame:
    """Neighbourhoods per repair-point count for each utility (0, 1, 2, ...)."""
    out = pd.concat(
        {UTILITY_LABELS[c]: df[c].value_counts().sort_index() for c in UTILITY_COLS}, axis=1
    )
    out.index.name = "repair_points"
    return out.fillna(0).astype(int).reset_index()


def add_utility_index(df: pd.DataFrame) -> pd.DataFrame:
    """Combined pipe-damage index.

    Each utility count is divided by its city-wide mean per neighbourhood, and
    the three ratios are averaged with equal weights. A value of 1 means
    "as much repair need as an average neighbourhood"; zero stays zero. Using
    means instead of z-scores keeps the index non-negative and stops a utility
    with many zeros from contributing negative values; equal weights are used
    because the table carries no information on the relative consequences of
    a gas, water or wastewater repair point.
    """
    out = df.copy()
    ratios = out[UTILITY_COLS] / out[UTILITY_COLS].mean()
    out["utility_index"] = ratios.mean(axis=1)
    out["utility_points_total"] = out[UTILITY_COLS].sum(axis=1)
    # Rank-based alternative used as a sensitivity check.
    out["utility_rank_score"] = out[UTILITY_COLS].rank(pct=True).mean(axis=1)
    out["utility_rank"] = out["utility_index"].rank(ascending=False, method="min").astype(int)
    return out


def district_totals(nb: pd.DataFrame) -> pd.DataFrame:
    cols = UTILITY_COLS + OTHER_COLS + ["damaged_buildings", "damage_index"]
    if "population" in nb:
        cols.append("population")
    d = nb.groupby("district", as_index=False)[cols].sum()
    d["neighbourhoods"] = nb.groupby("district").size().values
    d["utility_points_total"] = d[UTILITY_COLS].sum(axis=1)
    d["shelter_households_per_damaged_building"] = d["gecici_barinma"] / d["damaged_buildings"]
    if "population" in d:
        d["shelter_households_per_1000"] = 1000 * d["gecici_barinma"] / d["population"]
    return d.sort_values("utility_points_total", ascending=False).reset_index(drop=True)


def top_neighbourhoods(nb: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top-n neighbourhoods for each utility and for the combined index."""
    frames = []
    for col in UTILITY_COLS + ["utility_index"]:
        label = UTILITY_LABELS.get(col, "combined index")
        top = nb.sort_values([col, "damage_index"], ascending=False).head(n)
        frames.append(
            pd.DataFrame(
                {
                    "measure": label,
                    "position": range(1, len(top) + 1),
                    "district": top["district"].values,
                    "neighbourhood": top["neighbourhood"].values,
                    "value": top[col].values,
                    "damage_index": top["damage_index"].values,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def correlations(nb: pd.DataFrame) -> pd.DataFrame:
    """Spearman and Pearson (on log1p) correlations between building damage,
    pipe damage, shelter need and residents."""
    pairs = [
        ("damage_index", c) for c in UTILITY_COLS + ["utility_index"]
    ] + [
        ("damaged_buildings", c) for c in UTILITY_COLS
    ] + [
        ("damaged_buildings", "gecici_barinma"),
        ("moderate_or_worse", "gecici_barinma"),
        ("damage_index", "gecici_barinma"),
    ]
    if "population" in nb:
        pairs += [("population", "gecici_barinma"), ("population", "utility_index")]
    if "buildings" in nb:
        pairs += [("buildings", "utility_index"), ("buildings", "gecici_barinma")]
    nb = nb.assign(
        moderate_or_worse=nb["cok_agir_hasarli_bina_sayisi"]
        + nb["agir_hasarli_bina_sayisi"]
        + nb["orta_hasarli_bina_sayisi"]
    )
    rows = []
    for x, y in pairs:
        d = nb[[x, y]].dropna()
        rows.append(
            {
                "x": x,
                "y": y,
                "n": len(d),
                "spearman": spearmanr(d[x], d[y]).statistic,
                "pearson_log1p": pearsonr(np.log1p(d[x]), np.log1p(d[y])).statistic,
            }
        )
    return pd.DataFrame(rows)


def shelter_ratio_fit(nb: pd.DataFrame) -> dict:
    """Shelter households per moderately-or-worse damaged building.

    The project derives shelter need from households in moderately, heavily
    and very heavily damaged residential buildings, so this ratio is close to
    the average number of households per such building.
    """
    mw = (
        nb["cok_agir_hasarli_bina_sayisi"]
        + nb["agir_hasarli_bina_sayisi"]
        + nb["orta_hasarli_bina_sayisi"]
    )
    ratio = nb["gecici_barinma"] / mw.where(mw > 0)
    return {
        "city_households_per_moderate_or_worse_building": nb["gecici_barinma"].sum() / mw.sum(),
        "neighbourhood_ratio_median": ratio.median(),
        "neighbourhood_ratio_p10": ratio.quantile(0.1),
        "neighbourhood_ratio_p90": ratio.quantile(0.9),
    }
