"""Residents (TÜİK ADNKS) and building stock (IMM) per neighbourhood, and
per-capita / per-building rates derived from them.

Both tables are joined to the scenario rows on the national address database
(UAVT) neighbourhood code, which all three sources carry.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .data import ROOT

POPULATION_CSV = ROOT / "data" / "tuik_adnks_mahalle_population_2018_2020.csv"
BUILDINGS_CSV = ROOT / "data" / "ibb_mahalle_building_counts_2017.csv"

# ADNKS counts residents at their registered address on 31 December. The
# scenario is a night-time scenario that places the registered population at
# home, and the IMM district booklets quote the 2019 ADNKS figures, so 2019 is
# the default year.
POPULATION_YEAR = 2019

# Scenario UAVT code -> TÜİK UAVT code for neighbourhoods whose code differs
# between the two sources. All eight are former villages in Beykoz, Silivri and
# Şile: the scenario carries the old village code (16xxx), TÜİK the current
# neighbourhood code (191xxx). Names and districts are identical; a test checks
# that they still agree.
UAVT_CHANGES = {
    16634: 191719,  # Beykoz, Poyrazköy
    16775: 191849,  # Silivri, Büyük Kılıçlı
    16771: 191843,  # Silivri, Büyük Sinekli
    16765: 191839,  # Silivri, Fener
    16779: 191857,  # Silivri, Küçük Sinekli
    16785: 191865,  # Şile, Bozgoca
    16807: 191907,  # Şile, Gökmaşlı
    16816: 191925,  # Şile, Teke
}

# Minimum number of residents for a neighbourhood to enter per-capita rankings.
# Below it, the historic commercial core of Fatih and the organised industrial
# zones have a few dozen to a few hundred residents but many buildings, so the
# rates are dominated by the small denominator (see per_capita_threshold_table).
MIN_POPULATION = 1000

# Persons per household assumed by the IMM / Boğaziçi University KOERI loss
# estimation project when it converts shelter need (households) into people.
PERSONS_PER_HOUSEHOLD = 3

BUILDING_AGE_COLS = ["1980_oncesi", "1980-2000_arasi", "2000_sonrasi"]
BUILDING_FLOOR_COLS = ["1-4 kat_arasi", "5-9 kat_arasi", "9-19 kat_arasi"]

_ROW = re.compile(r"^İstanbul\((?P<district>.+?)/(?P<municipality>.+?)/(?P<name>.+?)\)-(?P<uavt>\d+)$")


def load_population(path: Path | str = POPULATION_CSV) -> pd.DataFrame:
    """Parse the pipe-separated pivot export of the TÜİK MEDAS database.

    Returns one row per (year, neighbourhood) with the TÜİK UAVT code.
    """
    rows, year = [], None
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            parts = line.rstrip("\r\n").split("|")
            if len(parts) < 3:
                continue
            if parts[0].strip().isdigit():
                year = int(parts[0])
            m = _ROW.match(parts[1].strip())
            if m is None or year is None:
                continue
            rows.append(
                {
                    "year": year,
                    "district": m["district"],
                    "neighbourhood": re.sub(r" Mah\.$", "", m["name"]),
                    "uavt": int(m["uavt"]),
                    "population": float(parts[2]),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty or out.duplicated(["year", "uavt"]).any():
        raise ValueError("Population table is empty or has duplicate codes")
    if (out["population"] < 0).any() or out["population"].isna().any():
        raise ValueError("Population counts must be non-missing and non-negative")
    out["population"] = out["population"].astype(int)
    return out


def load_buildings(path: Path | str = BUILDINGS_CSV) -> pd.DataFrame:
    """IMM building counts per neighbourhood (2017 inventory, 1 to 19 floors)."""
    b = pd.read_csv(path, sep=";", encoding="cp1254")
    if b["mahalle_uavt"].duplicated().any():
        raise ValueError("Duplicate neighbourhood codes in the building table")
    b["buildings"] = b[BUILDING_AGE_COLS].sum(axis=1)
    if not (b["buildings"] == b[BUILDING_FLOOR_COLS].sum(axis=1)).all():
        raise ValueError("Building totals by age and by floors disagree")
    b["share_pre_1980"] = b["1980_oncesi"] / b["buildings"]
    b["share_pre_2000"] = (b["1980_oncesi"] + b["1980-2000_arasi"]) / b["buildings"]
    return b.rename(columns={"mahalle_uavt": "uavt"})[
        ["uavt", "buildings", "share_pre_1980", "share_pre_2000"]
    ]


def attach_population(
    df: pd.DataFrame, pop: pd.DataFrame, year: int = POPULATION_YEAR
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add residents to the scenario rows.

    Returns the scenario table with `population` and `population_match`
    ('uavt' or 'uavt code changed') and the TÜİK rows of that year that have
    no scenario row.
    """
    p = pop[pop["year"] == year].set_index("uavt")
    codes = df["mahalle_koy_uavt"].astype(int)
    tuik_code = codes.map(lambda c: UAVT_CHANGES.get(c, c))
    out = df.copy()
    out["population"] = tuik_code.map(p["population"])
    out["population_match"] = np.where(
        codes.isin(list(UAVT_CHANGES)), "uavt code changed", "uavt"
    )
    out.loc[out["population"].isna(), "population_match"] = "unmatched"
    unused = p[~p.index.isin(tuik_code)].reset_index()
    return out, unused[["year", "district", "neighbourhood", "uavt", "population"]]


def join_report(nb: pd.DataFrame, unused: pd.DataFrame) -> pd.DataFrame:
    """Rows that did not join one-to-one on the UAVT code, for documentation."""
    changed = nb.loc[
        nb["population_match"] != "uavt", ["district", "neighbourhood", "mahalle_koy_uavt"]
    ].assign(
        tuik_uavt=lambda d: d["mahalle_koy_uavt"].map(UAVT_CHANGES),
        population=nb["population"],
        note="scenario carries the former village code",
    )
    extra = unused.rename(columns={"uavt": "tuik_uavt"}).drop(columns="year").assign(
        note="TÜİK neighbourhood without a scenario row"
    )
    report = pd.concat([changed, extra], ignore_index=True)
    for col in ["mahalle_koy_uavt", "tuik_uavt", "population"]:
        report[col] = report[col].astype("Int64")
    return report


def attach_buildings(df: pd.DataFrame, buildings: pd.DataFrame) -> pd.DataFrame:
    return df.merge(
        buildings, left_on="mahalle_koy_uavt", right_on="uavt", how="left"
    ).drop(columns="uavt")


def add_rates(df: pd.DataFrame, min_population: int = MIN_POPULATION) -> pd.DataFrame:
    """Per-capita and per-building rates.

    Rates are computed for every row with a population; `eligible` marks rows
    with at least `min_population` residents, and the per-capita ranks are
    given to eligible rows only.
    """
    out = df.copy()
    pop = out["population"].where(out["population"] > 0)
    out["casualties_per_1000"] = 1000 * out["deaths_serious"] / pop
    out["deaths_per_1000"] = 1000 * out["can_kaybi_sayisi"] / pop
    out["damage_index_per_1000"] = 1000 * out["damage_index"] / pop
    out["shelter_households_per_1000"] = 1000 * out["gecici_barinma"] / pop
    out["shelter_share_est"] = PERSONS_PER_HOUSEHOLD * out["gecici_barinma"] / pop
    if "buildings" in out:
        stock = out["buildings"].where(out["buildings"] > 0)
        out["damaged_share"] = out["damaged_buildings"] / stock
        out["heavy_or_worse_share"] = (
            out["cok_agir_hasarli_bina_sayisi"] + out["agir_hasarli_bina_sayisi"]
        ) / stock
        out["damage_index_per_100_buildings"] = 100 * out["damage_index"] / stock
        out["residents_per_building"] = out["population"] / stock
    out["eligible"] = out["population"] >= min_population
    for col in ["casualties_per_1000", "damage_index_per_1000"]:
        out[f"rank_{col}"] = (
            out[col].where(out["eligible"]).rank(ascending=False, method="min").astype("Int64")
        )
    return out


def district_rates(nb: pd.DataFrame) -> pd.DataFrame:
    """District totals and rates (sums first, then ratios)."""
    cols = [
        "population",
        "damage_index",
        "damaged_buildings",
        "cok_agir_hasarli_bina_sayisi",
        "agir_hasarli_bina_sayisi",
        "can_kaybi_sayisi",
        "deaths_serious",
        "gecici_barinma",
        "buildings",
    ]
    d = nb.groupby("district", as_index=False)[[c for c in cols if c in nb]].sum()
    d["casualties_per_1000"] = 1000 * d["deaths_serious"] / d["population"]
    d["deaths_per_1000"] = 1000 * d["can_kaybi_sayisi"] / d["population"]
    d["damage_index_per_1000"] = 1000 * d["damage_index"] / d["population"]
    d["shelter_households_per_1000"] = 1000 * d["gecici_barinma"] / d["population"]
    d["shelter_share_est"] = PERSONS_PER_HOUSEHOLD * d["gecici_barinma"] / d["population"]
    if "buildings" in d:
        d["damaged_share"] = d["damaged_buildings"] / d["buildings"]
        d["heavy_or_worse_share"] = (
            d["cok_agir_hasarli_bina_sayisi"] + d["agir_hasarli_bina_sayisi"]
        ) / d["buildings"]
    d["rank_absolute"] = d["deaths_serious"].rank(ascending=False, method="min").astype(int)
    d["rank_per_capita"] = (
        d["casualties_per_1000"].rank(ascending=False, method="min").astype(int)
    )
    return d.sort_values("rank_per_capita").reset_index(drop=True)


def compare_rankings(
    nb: pd.DataFrame,
    pairs: dict[str, tuple[str, str]] | None = None,
    top_ns: tuple[int, ...] = (10, 50),
) -> pd.DataFrame:
    """Spearman correlation and top-N overlap between absolute and per-capita
    rankings, over neighbourhoods eligible for per-capita ranking."""
    pairs = pairs or {
        "deaths + serious injuries": ("deaths_serious", "casualties_per_1000"),
        "deaths": ("can_kaybi_sayisi", "deaths_per_1000"),
        "damage index": ("damage_index", "damage_index_per_1000"),
        "shelter need": ("gecici_barinma", "shelter_households_per_1000"),
    }
    e = nb[nb["eligible"]]
    rows = []
    for label, (absolute, rate) in pairs.items():
        row = {
            "measure": label,
            "neighbourhoods": len(e),
            "spearman_absolute_vs_per_capita": spearmanr(e[absolute], e[rate]).statistic,
        }
        nz = e[e[absolute] > 0]
        row["spearman_nonzero_only"] = spearmanr(nz[absolute], nz[rate]).statistic
        row["nonzero_neighbourhoods"] = len(nz)
        for n in top_ns:
            a = set(e.nlargest(n, absolute).index)
            r = set(e.nlargest(n, rate).index)
            row[f"top{n}_overlap"] = len(a & r) / n
        rows.append(row)
    return pd.DataFrame(rows)


def per_capita_threshold_table(nb: pd.DataFrame, thresholds=(0, 250, 500, 1000, 2000, 5000)):
    """How the per-capita ranking reacts to the minimum-population threshold."""
    rows = []
    base = nb[nb["population"] >= MIN_POPULATION]
    base_top = set(base.nlargest(20, "casualties_per_1000").index)
    for t in thresholds:
        e = nb[nb["population"] >= max(t, 1)]
        top = e.nlargest(20, "casualties_per_1000")
        rows.append(
            {
                "min_population": t,
                "neighbourhoods": len(e),
                "residents_covered_share": e["population"].sum() / nb["population"].sum(),
                "max_casualties_per_1000": e["casualties_per_1000"].max(),
                "top20_median_population": top["population"].median(),
                "top20_overlap_with_main": len(base_top & set(top.index)) / 20,
                "spearman_casualties_vs_per_capita": spearmanr(
                    e["deaths_serious"], e["casualties_per_1000"]
                ).statistic,
            }
        )
    return pd.DataFrame(rows)
