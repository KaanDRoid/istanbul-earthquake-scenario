"""Boundary data: district polygons (in the repo) and neighbourhood polygons
(downloaded at runtime from OpenStreetMap-derived data, not committed)."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .data import ROOT, tr_title

DISTRICT_GEOJSON = ROOT / "ilce_geojson.json"
CACHE_DIR = ROOT / "data" / "external"
NEIGHBOURHOOD_CACHE = CACHE_DIR / "mahalle_geojson.json"

# Neighbourhood polygons of Istanbul compiled from OpenStreetMap through the
# Nominatim API (sahircansurmeli/istanbul-geojson). Pinned to a commit so the
# result is reproducible. Data (c) OpenStreetMap contributors, ODbL 1.0.
NEIGHBOURHOOD_URL = (
    "https://raw.githubusercontent.com/sahircansurmeli/istanbul-geojson/"
    "c9bf151a781b6991617bde028996f95f933bd5e4/mahalle_geojson.json"
)
OSM_ATTRIBUTION = "Boundaries (c) OpenStreetMap contributors, ODbL 1.0"

# Scenario name -> OpenStreetMap name, for neighbourhoods whose spelling
# differs or that were renamed (keys and values are normalised, see _norm).
NAME_ALIASES = {
    ("BESIKTAS", "NISBETIYE"): "NISPETIYE",
    ("BAKIRKOY", "SENLIKKOY"): "SENLIK",
    ("SULTANGAZI", "HABIBLER"): "HABIPLER",
    ("ESENLER", "NINEHATUN"): "NENEHATUN",
    ("BAGCILAR", "MERKEZ"): "BAGCILARMERKEZ",
    ("BAGCILAR", "EVREN"): "15TEMMUZ",  # renamed in 2016
    ("GUNGOREN", "MERKEZ"): "GUNGORENMERKEZ",
    ("BEYOGLU", "MUEYYETZADE"): "MUEYYEDZADE",
    ("SARIYER", "KUMKOYKILYOS"): "KUMKOY",
    ("SARIYER", "SARIYERMERKEZ"): "MERKEZ",
    ("CATALCA", "CIFTLIKKOY"): "CIFTLIKKOYMERKEZ",
    ("SILE", "KIZILCA"): "KIZILCAKOY",
}


def _norm(text: str) -> str:
    """Upper-case ASCII key without suffixes such as 'Mahallesi'."""
    text = text.replace("İ", "I").replace("ı", "I").upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\b(MAHALLESI|MAHALESI|MAH|KOYU|MAHALLE)\b", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def load_districts() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(DISTRICT_GEOJSON)
    gdf["district"] = gdf["display_name"].str.split(",").str[0].str.strip()
    return gdf[["district", "geometry"]]


def _download_neighbourhoods(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        NEIGHBOURHOOD_URL, headers={"User-Agent": "istanbul-earthquake-scenario"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
    except OSError as exc:
        raise RuntimeError(
            f"Cannot download neighbourhood polygons. Download {NEIGHBOURHOOD_URL} "
            f"to {path} and retry."
        ) from exc
    import hashlib

    expected = "053f7402d5c944d24f1cf632061cae489646567bcd82ccb33cf6a91623d4b76b"
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Downloaded boundary file does not match the pinned snapshot")
    tmp = path.with_suffix(".part")
    tmp.write_bytes(content)
    tmp.replace(path)


def load_neighbourhood_polygons(path: Path = NEIGHBOURHOOD_CACHE) -> gpd.GeoDataFrame:
    """Neighbourhood polygons with the district they fall in.

    The file is downloaded on first use and cached under data/external/.
    The published file has a missing comma between two features, which is
    repaired before parsing. District names in the Nominatim addresses are
    not consistent, so each polygon is assigned to the district polygon that
    contains its representative point.
    """
    if not path.exists():
        _download_neighbourhoods(path)
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r'\}(\s*)\{(\s*)"type": "Feature"', r'},\1{\2"type": "Feature"', raw)
    features = json.loads(raw)["features"]
    gdf = gpd.GeoDataFrame.from_features(features, crs=4326)
    gdf["osm_name"] = gdf["display_name"].str.split(",").str[0].str.strip()

    points = gdf[["geometry"]].copy()
    points["geometry"] = gdf.to_crs(32635).representative_point().to_crs(4326)
    joined = gpd.sjoin(points, load_districts(), how="left", predicate="within")
    joined = joined[~joined.index.duplicated()]
    gdf["district"] = joined["district"]
    gdf = gdf.dropna(subset=["district"])
    gdf["key"] = gdf["district"].map(_norm) + "|" + gdf["osm_name"].map(_norm)
    return gdf[["osm_id", "osm_name", "district", "key", "geometry"]]


def scenario_keys(df: pd.DataFrame) -> pd.Series:
    def key(row):
        d, n = _norm(row["ilce_adi"]), _norm(row["mahalle_adi"])
        return d + "|" + NAME_ALIASES.get((d, n), n)

    return df.apply(key, axis=1)


def attach_polygons(df: pd.DataFrame, polys: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Join scenario rows to polygons. Rows without a polygon keep geometry None."""
    keys = scenario_keys(df)
    if polys["key"].duplicated().any():
        raise ValueError("Ambiguous neighbourhood polygon keys")
    lookup = polys.set_index("key")
    out = df.copy()
    out["osm_name"] = keys.map(lookup["osm_name"])
    out["geometry"] = keys.map(lookup["geometry"])
    return gpd.GeoDataFrame(out, geometry="geometry", crs=4326)


__all__ = [
    "OSM_ATTRIBUTION",
    "attach_polygons",
    "load_districts",
    "load_neighbourhood_polygons",
    "tr_title",
]
