"""Regenerate every table, figure and the interactive map.

Usage (from the repository root):
    python scripts/build_outputs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eqscenario import data, geo, index, modeling, plots  # noqa: E402

FIG = ROOT / "figures"
RES = ROOT / "results"
MAP = ROOT / "maps" / "istanbul_damage_map.html"


def main() -> None:
    RES.mkdir(exist_ok=True)
    nb = index.add_index(data.load_scenario())
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
    plots.interactive_map(nb, districts, MAP)
    print(summary.round(3).to_string())


if __name__ == "__main__":
    main()
