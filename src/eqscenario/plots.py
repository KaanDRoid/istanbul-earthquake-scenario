"""Static figures (matplotlib / geopandas) and the interactive folium map."""

from __future__ import annotations

from pathlib import Path

import branca.colormap as cm
import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely

from .geo import OSM_ATTRIBUTION

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.unicode_minus": False,
        "figure.dpi": 110,
        "savefig.dpi": 150,
    }
)

SOURCE_NOTE = (
    "Data: IMM earthquake scenario (data.ibb.gov.tr). " + OSM_ATTRIBUTION + "."
)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def choropleth(
    nb: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    column: str,
    title: str,
    legend_title: str,
    path: Path,
    cmap: str = "YlOrRd",
    bins: list | None = None,
) -> Path:
    shown = nb[nb.geometry.notna()].to_crs(32635)
    fig, ax = plt.subplots(figsize=(13, 7.5))
    districts.to_crs(32635).plot(ax=ax, color="#e6e6e6", edgecolor="none")
    shown.plot(
        ax=ax,
        column=column,
        cmap=cmap,
        **(
            {"scheme": "user_defined", "classification_kwds": {"bins": bins}}
            if bins
            else {"scheme": "quantiles", "k": 7}
        ),
        edgecolor="white",
        linewidth=0.15,
        legend=True,
        legend_kwds={
            "title": legend_title,
            "loc": "lower left",
            "fontsize": 8,
            "title_fontsize": 9,
            "fmt": "{:.0f}",
        },
    )
    districts.to_crs(32635).boundary.plot(ax=ax, color="#333333", linewidth=0.5)
    ax.set_axis_off()
    ax.set_title(title, fontsize=13, loc="left")
    missing = int(nb.geometry.isna().sum())
    ax.annotate(
        f"{'Fixed' if bins else 'Quantile'} classes. Grey: no matching polygon ({missing} of {len(nb)} "
        f"neighbourhoods) or outside the data.\n{SOURCE_NOTE}",
        xy=(0, -0.04),
        xycoords="axes fraction",
        fontsize=7.5,
        color="#555555",
        va="top",
    )
    return _save(fig, path)


def top_neighbourhoods_bar(nb: pd.DataFrame, path: Path, n: int = 20) -> Path:
    top = nb.nsmallest(n, "rank").iloc[::-1]
    labels = top["neighbourhood"] + " (" + top["district"] + ")"
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(labels, top["damage_index"], color="#c0392b")
    for y, (v, c) in enumerate(zip(top["damage_index"], top["deaths_serious"])):
        ax.text(
            v + 3,
            y,
            f"{c:,} deaths + serious inj.",
            va="center",
            fontsize=7.5,
            color="#444444",
        )
    ax.set_xlabel("Weighted damage index (very-heavy-damage equivalents)")
    ax.set_title(f"Top {n} neighbourhoods by weighted damage index", loc="left")
    ax.set_xlim(0, top["damage_index"].max() * 1.35)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path)


def district_bar(dist: pd.DataFrame, path: Path) -> Path:
    d = dist.sort_values("damage_index")
    fig, ax1 = plt.subplots(figsize=(9, 9))
    ax1.barh(d["district"], d["damage_index"], color="#e67e22", label="Damage index")
    ax1.set_xlabel("Weighted damage index (sum over neighbourhoods)")
    ax2 = ax1.twiny()
    ax2.plot(
        d["deaths_serious"],
        d["district"],
        "o",
        color="#2c3e50",
        ms=4,
        label="Deaths + serious injuries",
    )
    ax2.set_xlabel("Deaths + serious injuries (dots)")
    ax1.set_title(
        "Districts: damage index (bars) and casualties (dots)", loc="left", pad=40
    )
    ax1.spines[["right"]].set_visible(False)
    return _save(fig, path)


def model_comparison(summary: pd.DataFrame, path: Path) -> Path:
    models = list(dict.fromkeys(summary["model"]))
    splits = list(dict.fromkeys(summary["split"]))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    width = 0.38
    colors = ["#5d6d7e", "#c0392b"]
    for ax, metric, label in zip(
        axes,
        ["r2", "mae", "poisson_dev"],
        [
            "R\u00b2 (higher is better)",
            "MAE (lower is better)",
            "Mean Poisson deviance (lower is better)",
        ],
    ):
        for i, split in enumerate(splits):
            s = summary[summary["split"] == split].set_index("model").loc[models]
            x = np.arange(len(models)) + (i - 0.5) * width
            ax.bar(
                x,
                s[f"{metric}_mean"],
                width,
                yerr=s[f"{metric}_std"],
                capsize=3,
                color=colors[i],
                label=split,
            )
        ax.set_xticks(np.arange(len(models)))
        ax.set_xticklabels([m.replace(" (", "\n(") for m in models], fontsize=7.5)
        ax.set_title(label, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=9, loc="upper right", ncol=2, frameon=False)
    fig.suptitle(
        "5-fold cross-validation, target: deaths + serious injuries per "
        "neighbourhood (mean and std over folds)",
        fontsize=11,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, path)


def oof_scatter(y: np.ndarray, pred: np.ndarray, title: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y + 1, np.clip(pred, 0, None) + 1, s=9, alpha=0.5, color="#2c3e50")
    lim = [1, max(y.max(), pred.max()) * 1.3]
    ax.plot(lim, lim, color="#c0392b", lw=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Scenario value + 1")
    ax.set_ylabel("Out-of-fold prediction + 1")
    ax.set_title(title, loc="left", fontsize=10)
    return _save(fig, path)


def _simplify(gdf: gpd.GeoDataFrame, tolerance_m: float = 15) -> gpd.GeoDataFrame:
    out = gdf.to_crs(32635)
    out["geometry"] = out.geometry.simplify(tolerance_m)
    out = out.to_crs(4326)
    out["geometry"] = shapely.set_precision(out.geometry.values, 1e-5)
    return out


def interactive_map(
    nb: gpd.GeoDataFrame, districts: gpd.GeoDataFrame, path: Path
) -> Path:
    shown = nb[nb.geometry.notna()].copy()
    fields = {
        "neighbourhood": "Neighbourhood",
        "district": "District",
        "rank": "Rank (of 959)",
        "damage_index": "Damage index",
        "severity": "Average severity weight",
        "damaged_buildings": "Damaged buildings",
        "cok_agir_hasarli_bina_sayisi": "Very heavy",
        "agir_hasarli_bina_sayisi": "Heavy",
        "can_kaybi_sayisi": "Deaths",
        "deaths_serious": "Deaths + serious injuries",
        "gecici_barinma": "Temporary shelter need",
    }
    shown = shown[list(fields) + ["geometry"]]
    shown["damage_index"] = shown["damage_index"].round(1)
    shown["severity"] = shown["severity"].round(3)
    shown = _simplify(gpd.GeoDataFrame(shown, geometry="geometry", crs=4326))

    m = folium.Map(
        location=[41.05, 28.95],
        zoom_start=10,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer("OpenStreetMap", control=False).add_to(m)
    q = np.quantile(shown["damage_index"], np.linspace(0, 1, 8)).tolist()
    colormap = cm.StepColormap(
        ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"],
        index=q,
        vmin=q[0],
        vmax=q[-1],
        caption="Weighted damage index (quantile classes)",
        tick_labels=[q[0], q[-1]],
    )
    q2 = np.quantile(shown["deaths_serious"], np.linspace(0, 1, 8)).tolist()
    q2 = sorted(set(q2))
    colormap2 = cm.StepColormap(
        ["#f1eef6", "#d0d1e6", "#a6bddb", "#74a9cf", "#3690c0", "#0570b0", "#034e7b"][
            : len(q2) - 1
        ],
        index=q2,
        vmin=q2[0],
        vmax=q2[-1],
        caption="Deaths + serious injuries (quantile classes)",
        tick_labels=[q2[0], q2[-1]],
    )
    tooltip = folium.GeoJsonTooltip(
        fields=list(fields), aliases=list(fields.values()), localize=True, sticky=True
    )
    folium.GeoJson(
        shown,
        name="Damage index",
        overlay=False,
        style_function=lambda f: {
            "fillColor": colormap(f["properties"]["damage_index"]),
            "color": "#666666",
            "weight": 0.3,
            "fillOpacity": 0.75,
        },
        highlight_function=lambda f: {"weight": 2, "color": "#000000"},
        tooltip=tooltip,
    ).add_to(m)
    folium.GeoJson(
        shown,
        name="Deaths + serious injuries",
        overlay=False,
        show=False,
        style_function=lambda f: {
            "fillColor": colormap2(f["properties"]["deaths_serious"]),
            "color": "#666666",
            "weight": 0.3,
            "fillOpacity": 0.75,
        },
        highlight_function=lambda f: {"weight": 2, "color": "#000000"},
        tooltip=folium.GeoJsonTooltip(
            fields=list(fields),
            aliases=list(fields.values()),
            localize=True,
            sticky=True,
        ),
    ).add_to(m)
    folium.GeoJson(
        _simplify(districts, 30),
        name="District boundaries",
        style_function=lambda f: {"fill": False, "color": "#222222", "weight": 1.2},
        tooltip=folium.GeoJsonTooltip(fields=["district"], aliases=["District"]),
    ).add_to(m)
    colormap.add_to(m)
    colormap2.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;bottom:8px;left:8px;z-index:9999;background:white;'
            'padding:4px 8px;font:12px sans-serif;opacity:0.9">'
            "IMM earthquake scenario results (data.ibb.gov.tr). Neighbourhood and district "
            "boundaries &copy; OpenStreetMap contributors, ODbL. "
            f"{len(nb) - len(shown)} neighbourhoods without a polygon are not shown.</div>"
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(path))
    html = path.read_text(encoding="utf-8")
    path.write_text(
        "\n".join(line.rstrip() for line in html.splitlines()) + "\n", encoding="utf-8"
    )
    return path
