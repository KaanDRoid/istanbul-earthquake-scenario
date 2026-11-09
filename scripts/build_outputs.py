"""Regenerate every table, figure and the interactive map.

Usage (from the repository root):
    python scripts/build_outputs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eqscenario import data, geo, index, infrastructure, modeling, plots  # noqa: E402
from eqscenario import population as popn  # noqa: E402

FIG = ROOT / "figures"
RES = ROOT / "results"
MAP = ROOT / "maps" / "istanbul_damage_map.html"


def main() -> None:
    RES.mkdir(exist_ok=True)
    nb = index.add_index(data.load_scenario())
    nb, tuik_without_scenario = popn.attach_population(nb, popn.load_population())
    nb = popn.attach_buildings(nb, popn.load_buildings())
    nb = infrastructure.add_utility_index(popn.add_rates(nb))
    print(nb["population_match"].value_counts().to_string())
    districts = geo.load_districts()
    nb = geo.attach_polygons(nb, geo.load_neighbourhood_polygons())
    print(f"neighbourhoods: {len(nb)}, with polygon: {nb.geometry.notna().sum()}")

    table_cols = [
        "rank",
        "district",
        "neighbourhood",
        "damage_index",
        "severity",
        "damaged_buildings",
        "cok_agir_hasarli_bina_sayisi",
        "deaths_serious",
        "mahalle_koy_uavt",
        "can_kaybi_sayisi",
        "gecici_barinma",
    ]
    nb_table = nb.sort_values("rank")[table_cols].assign(
        has_polygon=nb.geometry.notna()
    )
    nb_table.round(3).to_csv(RES / "neighbourhood_index.csv", index=False)
    dist = index.district_index(nb)
    dist.round(3).to_csv(RES / "district_index.csv", index=False)
    index.sensitivity(nb).round(3).to_csv(RES / "weight_sensitivity.csv", index=False)

    folds, summary, oof = modeling.cross_validate(nb)
    folds.round(4).to_csv(RES / "cv_folds.csv", index=False)
    summary.round(3).to_csv(RES / "cv_summary.csv", index=False)
    modeling.per_building_rates(nb).round(4).to_csv(
        RES / "per_building_rates.csv", index=False
    )
    modeling.single_feature_cv(nb).round(3).to_csv(
        RES / "single_feature_cv.csv", index=False
    )

    dist_geo = districts.merge(dist, on="district", how="left")
    plots.choropleth(
        nb,
        districts,
        "damage_index",
        "Weighted building-damage index by neighbourhood",
        "Damage index",
        FIG / "damage_index_map.png",
    )
    plots.choropleth(
        nb,
        districts,
        "deaths_serious",
        "Scenario deaths + serious injuries by neighbourhood",
        "Deaths + serious inj.",
        FIG / "casualties_map.png",
        cmap="PuBu",
        bins=[0, 2, 5, 15, 40, 100, 400],
    )
    plots.top_neighbourhoods_bar(nb, FIG / "top_neighbourhoods.png")
    plots.district_bar(dist_geo, FIG / "district_index.png")
    plots.model_comparison(summary, FIG / "model_comparison.png")
    best = ("grouped by district 5-fold", "Poisson GLM (log1p features)")
    plots.oof_scatter(
        nb[modeling.TARGET].to_numpy(),
        oof[best],
        "Poisson GLM, out-of-fold predictions (grouped by district)",
        FIG / "oof_poisson_glm.png",
    )
    per_capita_outputs(nb, districts, tuik_without_scenario)
    infrastructure_outputs(nb, districts)
    plots.interactive_map(nb, districts, MAP)
    print(summary.round(3).to_string())


def per_capita_outputs(nb, districts, tuik_without_scenario) -> None:
    report = popn.join_report(nb, tuik_without_scenario)
    report.to_csv(RES / "population_join_report.csv", index=False)
    cols = [
        "district",
        "neighbourhood",
        "mahalle_koy_uavt",
        "population",
        "buildings",
        "eligible",
        "rank_casualties_per_1000",
        "casualties_per_1000",
        "deaths_per_1000",
        "rank_damage_index_per_1000",
        "damage_index_per_1000",
        "shelter_households_per_1000",
        "shelter_share_est",
        "damaged_share",
        "heavy_or_worse_share",
        "damage_index_per_100_buildings",
        "residents_per_building",
        "share_pre_1980",
        "deaths_serious",
        "can_kaybi_sayisi",
        "damage_index",
        "rank",
        "gecici_barinma",
    ]
    nb.sort_values(["rank_casualties_per_1000", "casualties_per_1000"], ascending=[True, False])[
        cols
    ].round(4).to_csv(RES / "per_capita_neighbourhoods.csv", index=False)
    dist = popn.district_rates(nb)
    dist.round(4).to_csv(RES / "per_capita_districts.csv", index=False)
    popn.compare_rankings(nb).round(3).to_csv(RES / "per_capita_rank_comparison.csv", index=False)
    popn.per_capita_threshold_table(nb).round(3).to_csv(
        RES / "per_capita_threshold_sensitivity.csv", index=False
    )
    folds, summary, _ = modeling.exposure_cv(nb)
    folds.round(4).to_csv(RES / "exposure_cv_folds.csv", index=False)
    summary.round(3).to_csv(RES / "exposure_cv_summary.csv", index=False)

    plots.choropleth(
        nb.assign(casualties_per_1000=nb["casualties_per_1000"].where(nb["eligible"])),
        districts,
        "casualties_per_1000",
        "Scenario deaths + serious injuries per 1,000 residents",
        "Per 1,000 residents",
        FIG / "per_capita_casualties_map.png",
        cmap="RdPu",
        bins=[0, 0.25, 0.5, 1, 2, 4, 8, 14],
        fmt="{:.2f}",
        labels=["0", "up to 0.25", "0.25-0.5", "0.5-1", "1-2", "2-4", "4-8", "over 8"],
        note="Fixed classes. Grey: under 1,000 residents, no matching polygon, or outside the data.",
        source_note=plots.SOURCE_NOTE + " " + plots.POPULATION_NOTE,
    )
    plots.choropleth(
        nb.assign(pct=100 * nb["heavy_or_worse_share"]),
        districts,
        "pct",
        "Share of buildings with heavy or very heavy damage",
        "% of buildings",
        FIG / "heavy_damage_share_map.png",
        cmap="YlOrRd",
        bins=[0, 1, 2, 4, 6, 10, 15, 25],
        labels=["0", "up to 1", "1-2", "2-4", "4-6", "6-10", "10-15", "over 15"],
        source_note=plots.SOURCE_NOTE
        + " Building stock: IMM 2017 neighbourhood building counts (1 to 19 floors).",
    )
    plots.per_capita_bar(nb, FIG / "per_capita_top_neighbourhoods.png")
    plots.per_capita_scatter(nb, FIG / "per_capita_vs_absolute.png")
    plots.district_per_capita_bar(dist, FIG / "district_per_capita.png")


def infrastructure_outputs(nb, districts) -> None:
    infrastructure.describe_columns(nb).round(3).to_csv(
        RES / "infrastructure_columns.csv", index=False
    )
    infrastructure.value_counts_table(nb).to_csv(
        RES / "infrastructure_value_counts.csv", index=False
    )
    infrastructure.district_totals(nb).round(3).to_csv(
        RES / "infrastructure_districts.csv", index=False
    )
    infrastructure.top_neighbourhoods(nb).round(3).to_csv(
        RES / "infrastructure_top_neighbourhoods.csv", index=False
    )
    infrastructure.correlations(nb).round(3).to_csv(
        RES / "infrastructure_correlations.csv", index=False
    )
    pd.Series(infrastructure.shelter_ratio_fit(nb)).round(3).rename("value").to_csv(
        RES / "shelter_ratio.csv", index_label="statistic"
    )
    plots.pipeline_maps(nb, districts, FIG / "pipeline_damage_maps.png")
    plots.shelter_maps(nb, districts, FIG / "shelter_need_maps.png")
    plots.infrastructure_scatter(nb, FIG / "infrastructure_relationships.png")


if __name__ == "__main__":
    main()
