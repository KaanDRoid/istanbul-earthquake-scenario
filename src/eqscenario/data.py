"""Loading and cleaning of the IMM earthquake scenario table."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_CSV = ROOT / "deprem-senaryosu-analiz-sonuclar.csv"

DAMAGE_COLS = [
    "cok_agir_hasarli_bina_sayisi",
    "agir_hasarli_bina_sayisi",
    "orta_hasarli_bina_sayisi",
    "hafif_hasarli_bina_sayisi",
]
DAMAGE_LABELS = {
    "cok_agir_hasarli_bina_sayisi": "very heavy",
    "agir_hasarli_bina_sayisi": "heavy",
    "orta_hasarli_bina_sayisi": "moderate",
    "hafif_hasarli_bina_sayisi": "light",
}
CASUALTY_COLS = [
    "can_kaybi_sayisi",
    "agir_yarali_sayisi",
    "hastanede_tedavi_sayisi",
    "hafif_yarali_sayisi",
]
NUMERIC_COLS = (
    DAMAGE_COLS
    + CASUALTY_COLS
    + [
        "dogalgaz_boru_hasari",
        "icme_suyu_boru_hasari",
        "atik_su_boru_hasari",
        "gecici_barinma",
    ]
)

# District names that changed after the boundary data was published.
DISTRICT_RENAMES = {"EYÜP": "EYÜPSULTAN"}

_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_TR_UPPER = str.maketrans({"i": "İ", "ı": "I"})


def tr_title(text: str) -> str:
    """Title-case a Turkish upper-case string (KAĞITHANE -> Kağıthane)."""
    words = text.translate(_TR_LOWER).lower().split(" ")
    out = []
    for w in words:
        if not w:
            out.append(w)
            continue
        first = w[0].translate(_TR_UPPER).upper()
        out.append(first + w[1:])
    return " ".join(out)


def load_scenario(path: Path | str = SCENARIO_CSV) -> pd.DataFrame:
    """Read the scenario CSV.

    The file is published as Windows-1254 (Turkish) bytes. Reading it as
    Latin-1 produces characters such as 'Ý' and 'Þ'; cp1254 decodes the
    Turkish letters correctly, so no manual character replacement is needed.
    """
    df = pd.read_csv(path, sep=";", encoding="cp1254")
    df["ilce_adi"] = df["ilce_adi"].str.strip().replace(DISTRICT_RENAMES)
    df["mahalle_adi"] = df["mahalle_adi"].str.strip()
    df[NUMERIC_COLS] = df[NUMERIC_COLS].apply(pd.to_numeric, errors="raise")
    if df[NUMERIC_COLS].isna().any().any() or (df[NUMERIC_COLS] < 0).any().any():
        raise ValueError("Scenario counts must be non-missing and non-negative")
    if df["mahalle_koy_uavt"].isna().any() or df["mahalle_koy_uavt"].duplicated().any():
        raise ValueError("Neighbourhood UAVT IDs must be present and unique")

    df["district"] = df["ilce_adi"].map(tr_title)
    df["neighbourhood"] = df["mahalle_adi"].map(tr_title)
    df["damaged_buildings"] = df[DAMAGE_COLS].sum(axis=1)
    df["deaths_serious"] = df["can_kaybi_sayisi"] + df["agir_yarali_sayisi"]
    return df


def district_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Sum the neighbourhood rows per district."""
    cols = NUMERIC_COLS + ["damaged_buildings", "deaths_serious"]
    out = df.groupby("district", as_index=False)[cols].sum()
    out["neighbourhoods"] = df.groupby("district").size().values
    return out
