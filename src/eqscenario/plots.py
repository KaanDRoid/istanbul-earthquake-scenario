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


def _save(fig, path: Path, dpi: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white", **({"dpi": dpi} if dpi else {}))
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
    note: str | None = None,
    fmt: str = "{:.0f}",
    source_note: str | None = None,
    labels: list | None = None,
) -> Path:
    fig, ax = plt.subplots(figsize=(13, 7.5))
    _choropleth_ax(ax, nb, districts, column, legend_title, cmap, bins, fmt, labels=labels)
    ax.set_title(title, fontsize=13, loc="left")
    missing = int(nb.geometry.isna().sum())
    note = note or (
        f"{'Fixed' if bins else 'Quantile'} classes. Grey: no matching polygon ({missing} of "
        f"{len(nb)} neighbourhoods) or outside the data."
    )
    ax.annotate(
        f"{note}\n{source_note or SOURCE_NOTE}",
        xy=(0, -0.04),
        xycoords="axes fraction",
        fontsize=7.5,
        color="#555555",
        va="top",
    )
    return _save(fig, path)


def _choropleth_ax(ax, nb, districts, column, legend_title, cmap, bins, fmt="{:.0f}",
                   legend_fontsize=8, labels=None):
    shown = nb[nb.geometry.notna() & nb[column].notna()].to_crs(32635)
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
            "fontsize": legend_fontsize,
            "title_fontsize": legend_fontsize + 1,
            **({"labels": labels} if labels else {"fmt": fmt}),
        },
    )
    districts.to_crs(32635).boundary.plot(ax=ax, color="#333333", linewidth=0.5)
    ax.set_axis_off()
    return ax


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


POPULATION_NOTE = "Residents: TÜİK ADNKS 2019 (address-based population registration)."


def per_capita_bar(nb: pd.DataFrame, path: Path, n: int = 20, min_population: int = 1000) -> Path:
    """Top-n neighbourhoods by deaths + serious injuries per 1,000 residents."""
    e = nb[nb["eligible"]]
    top = e.nlargest(n, "casualties_per_1000").iloc[::-1]
    abs_rank = nb["deaths_serious"].rank(ascending=False, method="min").astype(int)
    labels = top["neighbourhood"] + " (" + top["district"] + ")"
    fig, ax = plt.subplots(figsize=(9.5, 7))
    ax.barh(labels, top["casualties_per_1000"], color="#8e44ad")
    city = 1000 * nb["deaths_serious"].sum() / nb["population"].sum()
    ax.axvline(city, color="#333333", lw=0.8, ls="--")
    ax.text(city, n - 0.4, f" city: {city:.2f}", fontsize=7.5, va="bottom")
    for y, (_, r) in enumerate(top.iterrows()):
        ax.text(
            r["casualties_per_1000"] + 0.15,
            y,
            f"{int(r['deaths_serious']):,} of {int(r['population']):,} residents; "
            f"absolute rank {abs_rank[r.name]}",
            va="center",
            fontsize=7.2,
            color="#444444",
        )
    ax.set_xlim(0, top["casualties_per_1000"].max() * 1.75)
    ax.set_xlabel("Scenario deaths + serious injuries per 1,000 residents")
    ax.set_title(
        f"Top {n} neighbourhoods per capita (at least {min_population:,} residents)", loc="left"
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.annotate(
        "Absolute rank: position among 959 neighbourhoods by deaths + serious injuries.\n"
        + POPULATION_NOTE,
        xy=(0, -0.1),
        xycoords="axes fraction",
        fontsize=7.5,
        color="#555555",
        va="top",
    )
    return _save(fig, path)


def per_capita_scatter(nb: pd.DataFrame, path: Path, label_n: int = 8) -> Path:
    """Casualties against residents with lines of constant rate."""
    e = nb[nb["eligible"]]
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.scatter(e["population"], e["deaths_serious"] + 1, s=9, alpha=0.45, color="#2c3e50")
    city = nb["deaths_serious"].sum() / nb["population"].sum()
    xs = np.logspace(np.log10(e["population"].min()), np.log10(e["population"].max()), 50)
    for mult, style in [(0.25, ":"), (1, "--"), (4, ":")]:
        ax.plot(xs, xs * city * mult + 1, style, color="#c0392b", lw=1)
        ax.text(xs[-1], xs[-1] * city * mult + 1, f" {mult:g} x city rate", fontsize=7,
                color="#c0392b", va="center")
    for _, r in e.nlargest(label_n // 2, "casualties_per_1000").iterrows():
        ax.annotate(r["neighbourhood"], (r["population"], r["deaths_serious"] + 1), fontsize=7,
                    xytext=(3, 3), textcoords="offset points")
    for i, (_, r) in enumerate(e.nlargest(3, "deaths_serious").iterrows()):
        ax.annotate(r["neighbourhood"], (r["population"], r["deaths_serious"] + 1), fontsize=7,
                    xytext=(-75, 12 - 11 * i), textcoords="offset points",
                    arrowprops={"arrowstyle": "-", "color": "#999999", "lw": 0.5})
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(right=e["population"].max() * 6)
    ax.set_xlabel("Residents (2019)")
    ax.set_ylabel("Deaths + serious injuries + 1")
    ax.set_title("Neighbourhood casualties against residents", loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path)


def district_per_capita_bar(dist: pd.DataFrame, path: Path) -> Path:
    d = dist.sort_values("casualties_per_1000")
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.barh(d["district"], d["casualties_per_1000"], color="#8e44ad")
    for y, (_, r) in enumerate(d.iterrows()):
        ax.text(r["casualties_per_1000"] + 0.08, y,
                f"absolute rank {int(r['rank_absolute'])}", va="center", fontsize=7, color="#444444",
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.3}, zorder=3)
    city = 1000 * dist["deaths_serious"].sum() / dist["population"].sum()
    ax.axvline(city, color="#333333", lw=0.8, ls="--", zorder=1)
    ax.set_xlim(0, d["casualties_per_1000"].max() * 1.3)
    ax.set_xlabel("Deaths + serious injuries per 1,000 residents (dashed: city)")
    ax.set_title("Districts per capita", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path)


def pipeline_maps(nb: gpd.GeoDataFrame, districts: gpd.GeoDataFrame, path: Path) -> Path:
    """Repair points per utility and the combined index, four panels."""
    from .infrastructure import UTILITY_COLS, UTILITY_LABELS

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    bins = [0, 1, 2, 4, 14]
    labels = ["0", "1", "2", "3-4", "5 or more"]
    for ax, col in zip(axes.flat, UTILITY_COLS):
        _choropleth_ax(ax, nb, districts, col, "Repair points", "OrRd", bins, legend_fontsize=7,
                       labels=labels)
        ax.set_title(f"{UTILITY_LABELS[col].capitalize()} pipes: "
                     f"{int(nb[col].sum()):,} repair points", loc="left", fontsize=11)
    _choropleth_ax(axes.flat[3], nb, districts, "utility_index", "Index (1 = city mean)",
                   "PuRd", [0, 0.5, 1, 2, 4, 13], fmt="{:.1f}", legend_fontsize=7,
                   labels=["0", "up to 0.5", "0.5-1", "1-2", "2-4", "over 4"])
    axes.flat[3].set_title("Combined pipe-damage index", loc="left", fontsize=11)
    fig.suptitle("Scenario pipe repair points by neighbourhood (classes: 0, 1, 2, 3-4, 5+)",
                 x=0.01, ha="left", fontsize=13)
    fig.text(0.01, 0.01, SOURCE_NOTE, fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    return _save(fig, path, dpi=100)


def shelter_maps(nb: gpd.GeoDataFrame, districts: gpd.GeoDataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    _choropleth_ax(axes[0], nb, districts, "gecici_barinma", "Households", "YlGnBu",
                   [0, 250, 500, 1000, 2000, 4000, 9100], legend_fontsize=7,
                   labels=["0", "1-250", "251-500", "501-1,000", "1,001-2,000", "2,001-4,000",
                           "over 4,000"])
    axes[0].set_title(f"Temporary shelter need: {int(nb['gecici_barinma'].sum()):,} households",
                      loc="left", fontsize=11)
    e = nb.assign(share_pct=100 * nb["shelter_share_est"].where(nb["eligible"]))
    _choropleth_ax(axes[1], e, districts, "share_pct", "% of residents", "YlGnBu",
                   [0, 5, 10, 20, 30, 45, 85], legend_fontsize=7,
                   labels=["0", "up to 5", "5-10", "10-20", "20-30", "30-45", "over 45"])
    axes[1].set_title("Estimated share of residents needing shelter", loc="left", fontsize=11)
    fig.text(0.01, 0.0,
             "Right: households x 3 persons (the loss estimation project's assumption) / 2019 "
             "residents; neighbourhoods under 1,000 residents in grey.\n"
             + SOURCE_NOTE + " " + POPULATION_NOTE, fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return _save(fig, path, dpi=130)


def infrastructure_scatter(nb: pd.DataFrame, path: Path) -> Path:
    from .infrastructure import UTILITY_COLS, UTILITY_LABELS

    fig, axes = plt.subplots(2, 2, figsize=(12, 9.5))
    ax = axes[0, 0]
    ax.scatter(nb["damage_index"], nb["utility_index"], s=8, alpha=0.4, color="#2c3e50")
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("Weighted damage index")
    ax.set_ylabel("Combined pipe-damage index")
    ax.set_title("Building damage and pipe damage", loc="left", fontsize=10)

    ax = axes[0, 1]
    dec = pd.qcut(nb["damage_index"].rank(method="first"), 10, labels=False) + 1
    for col, c in zip(UTILITY_COLS, ["#e67e22", "#2980b9", "#7f8c8d"]):
        ax.plot(range(1, 11), nb.groupby(dec)[col].mean(), "o-", ms=4, color=c,
                label=UTILITY_LABELS[col])
    ax.set_xlabel("Damage-index decile (1 = lowest)")
    ax.set_ylabel("Mean repair points per neighbourhood")
    ax.legend(fontsize=8, frameon=False)
    ax.set_title("Repair points rise with building damage", loc="left", fontsize=10)

    mw = (nb["cok_agir_hasarli_bina_sayisi"] + nb["agir_hasarli_bina_sayisi"]
          + nb["orta_hasarli_bina_sayisi"])
    ax = axes[1, 0]
    ax.scatter(mw + 1, nb["gecici_barinma"] + 1, s=8, alpha=0.4, color="#16a085")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Buildings with moderate, heavy or very heavy damage + 1")
    ax.set_ylabel("Shelter need (households) + 1")
    ax.set_title("Shelter need and damaged buildings", loc="left", fontsize=10)

    ax = axes[1, 1]
    if "population" in nb:
        ax.scatter(nb["population"], nb["gecici_barinma"] + 1, s=8, alpha=0.4, color="#16a085")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Residents (2019)")
        ax.set_ylabel("Shelter need (households) + 1")
        ax.set_title("Shelter need and residents", loc="left", fontsize=10)
    for a in axes.flat:
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _save(fig, path)


def _simplify(gdf: gpd.GeoDataFrame, tolerance_m: float = 15) -> gpd.GeoDataFrame:
    out = gdf.to_crs(32635)
    out["geometry"] = out.geometry.simplify(tolerance_m)
    out = out.to_crs(4326)
    out["geometry"] = shapely.set_precision(out.geometry.values, 1e-5)
    return out


_BLUES = ["#f1eef6", "#d0d1e6", "#a6bddb", "#74a9cf", "#3690c0", "#0570b0", "#034e7b"]
_REDS = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"]
_PURPLES = ["#f2f0f7", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#4a1486"]
_ORANGES = ["#fff5eb", "#fee6ce", "#fdd0a2", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603"]
_GREENS = ["#ffffcc", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#0c2c84"]


def _step_colormap(values: pd.Series, colors: list, caption: str, bins=None):
    if bins is None:
        bins = sorted(set(np.quantile(values.dropna(), np.linspace(0, 1, 8)).round(4).tolist()))
        caption += " (quantile classes)"
    return cm.StepColormap(
        colors[: len(bins) - 1],
        index=bins,
        vmin=bins[0],
        vmax=bins[-1],
        caption=caption,
        tick_labels=[bins[0], bins[-1]],
    )


def interactive_map(
    nb: gpd.GeoDataFrame, districts: gpd.GeoDataFrame, path: Path
) -> Path:
    """Folium map with one switchable layer per measure.

    Layers for residents, pipe damage and shelter need are added when the
    corresponding columns are present.
    """
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
        "gecici_barinma": "Temporary shelter need (households)",
    }
    optional = {
        "population": "Residents (2019)",
        "casualties_per_1000": "Deaths + serious inj. per 1,000 residents",
        "shelter_pct": "Shelter need, est. % of residents",
        "dogalgaz_boru_hasari": "Gas pipe repair points",
        "icme_suyu_boru_hasari": "Water pipe repair points",
        "atik_su_boru_hasari": "Wastewater pipe repair points",
        "utility_index": "Combined pipe-damage index",
    }
    if "shelter_share_est" in shown:
        shown["shelter_pct"] = (100 * shown["shelter_share_est"]).round(1)
    fields.update({k: v for k, v in optional.items() if k in shown})
    shown = shown[list(fields) + ["geometry"]]
    for col, digits in [("damage_index", 1), ("severity", 3), ("casualties_per_1000", 2),
                        ("utility_index", 2)]:
        if col in shown:
            shown[col] = shown[col].round(digits)
    shown = _simplify(gpd.GeoDataFrame(shown, geometry="geometry", crs=4326))

    m = folium.Map(location=[41.05, 28.95], zoom_start=10, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", control=False).add_to(m)

    ids = ["neighbourhood", "district"]
    damage = ["rank", "damage_index", "severity", "damaged_buildings",
              "cok_agir_hasarli_bina_sayisi", "agir_hasarli_bina_sayisi"]
    people = ["can_kaybi_sayisi", "deaths_serious", "population", "casualties_per_1000"]
    pipes = ["dogalgaz_boru_hasari", "icme_suyu_boru_hasari", "atik_su_boru_hasari",
             "utility_index", "damage_index"]
    shelter = ["gecici_barinma", "population", "shelter_pct", "damaged_buildings"]
    layers = [("damage_index", "Damage index", _REDS, "Weighted damage index", None,
               damage + people + ["gecici_barinma"]),
              ("deaths_serious", "Deaths + serious injuries", _BLUES,
               "Deaths + serious injuries", None, people + ["damage_index"])]
    if "casualties_per_1000" in shown:
        layers.append(("casualties_per_1000", "Deaths + serious injuries per 1,000 residents",
                       _PURPLES, "Deaths + serious injuries per 1,000 residents", None, people))
    if "utility_index" in shown:
        layers.append(("utility_index", "Pipe damage (combined index)", _ORANGES,
                       "Combined pipe-damage index (1 = city mean)", [0, 0.5, 1, 2, 4, 13],
                       pipes))
    layers.append(("gecici_barinma", "Temporary shelter need (households)", _GREENS,
                   "Temporary shelter need (households)", [0, 250, 500, 1000, 2000, 4000, 9100],
                   shelter))

    for i, (col, name, colors, caption, bins, extra) in enumerate(layers):
        tooltip_fields = list(dict.fromkeys(f for f in ids + extra if f in shown))
        aliases = [fields[f] for f in tooltip_fields]
        keep = list(dict.fromkeys(tooltip_fields + [col]))
        values = shown[col]
        if col == "casualties_per_1000" and "population" in shown:
            values = values.where(shown["population"] >= 1000)
        cmap_ = _step_colormap(values, colors, caption, bins)

        def style(f, cmap_=cmap_, col=col):
            v = f["properties"][col]
            pc_hidden = col == "casualties_per_1000" and f["properties"].get("population", 1e9) < 1000
            return {
                "fillColor": "#bdbdbd" if (pc_hidden or v is None) else cmap_(v),
                "color": "#666666",
                "weight": 0.3,
                "fillOpacity": 0.75,
            }

        folium.GeoJson(
            shown[keep + ["geometry"]],
            name=name,
            overlay=False,
            show=i == 0,
            style_function=style,
            highlight_function=lambda f: {"weight": 2, "color": "#000000"},
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_fields, aliases=aliases, localize=True, sticky=True
            ),
        ).add_to(m)
        cmap_.add_to(m)
    folium.GeoJson(
        _simplify(districts, 30),
        name="District boundaries",
        style_function=lambda f: {"fill": False, "color": "#222222", "weight": 1.2},
        tooltip=folium.GeoJsonTooltip(fields=["district"], aliases=["District"]),
    ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    pop_note = (
        " Residents: TÜİK ADNKS 2019; per-capita layer grey under 1,000 residents."
        if "population" in shown
        else ""
    )
    m.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;bottom:8px;left:8px;z-index:9999;background:white;'
            'padding:4px 8px;font:12px sans-serif;opacity:0.9">'
            "IMM earthquake scenario results (data.ibb.gov.tr). Neighbourhood and district "
            "boundaries &copy; OpenStreetMap contributors, ODbL. "
            f"{len(nb) - len(shown)} neighbourhoods without a polygon are not shown.{pop_note}</div>"
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(path))
    html = path.read_text(encoding="utf-8")
    path.write_text(
        "\n".join(line.rstrip() for line in html.splitlines()) + "\n", encoding="utf-8"
    )
    return path
