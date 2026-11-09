"""Checks for the scenario analysis, run with python -m unittest discover -s tests."""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eqscenario import data, geo, index, modeling


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = data.load_scenario()

    def test_source_shape_encoding_and_counts(self):
        df = self.df
        self.assertEqual(len(df), 959)
        self.assertEqual(df.district.nunique(), 39)
        self.assertIn("Kağıthane", set(df.district))
        self.assertIn("Eyüpsultan", set(df.district))
        self.assertEqual(df.deaths_serious.sum(), 22235)
        self.assertEqual(df.damaged_buildings.sum(), 495866)

    def test_missing_negative_duplicate_counts_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.csv"
            for value in [-1, np.nan]:
                df = self.df.copy()
                df.loc[0, data.DAMAGE_COLS[0]] = value
                df.to_csv(path, sep=";", encoding="cp1254", index=False)
                with self.assertRaises(ValueError):
                    data.load_scenario(path)
            df = self.df.copy()
            df.loc[1, "mahalle_koy_uavt"] = df.loc[0, "mahalle_koy_uavt"]
            df.to_csv(path, sep=";", encoding="cp1254", index=False)
            with self.assertRaises(ValueError):
                data.load_scenario(path)

    def test_index_weights_and_district_conservation(self):
        nb = index.add_index(self.df)
        expected = self.df[data.DAMAGE_COLS].to_numpy() @ [1, 0.5, 0.1, 0.02]
        np.testing.assert_allclose(nb.damage_index, expected)
        self.assertTrue(nb.severity.between(0, 1).all())
        dist = index.district_index(nb)
        self.assertAlmostEqual(dist.damage_index.sum(), nb.damage_index.sum())
        self.assertEqual(dist.iloc[0].district, "Fatih")
        self.assertEqual(nb.sort_values("rank").iloc[0].neighbourhood, "Yeşilköy")

    def test_group_split_has_no_district_overlap(self):
        cv, groups = modeling.splitters(self.df.district)["grouped by district 5-fold"]
        seen = []
        for tr, te in cv.split(self.df, groups=groups):
            self.assertFalse(set(groups[tr]) & set(groups[te]))
            seen.extend(te)
        self.assertEqual(sorted(seen), list(range(959)))

    def test_poisson_deviance_clips_only_for_deviance(self):
        y, pred = np.array([0.0, 2.0, 5.0]), np.array([-1.0, 2.0, 3.0])
        scores = modeling._scores(y, pred)
        self.assertTrue(np.isfinite(list(scores.values())).all())
        self.assertAlmostEqual(scores["mae"], 1.0)

    def test_download_failure_does_not_cache_partial_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            with patch(
                "urllib.request.urlopen", side_effect=OSError("network unavailable")
            ):
                with self.assertRaisesRegex(RuntimeError, "Cannot download"):
                    geo._download_neighbourhoods(path)
            self.assertFalse(path.exists())

    def test_committed_map_and_notebook_outputs(self):
        import json

        html = (ROOT / "maps" / "istanbul_damage_map.html").read_text(encoding="utf-8")
        self.assertNotIn("np.float", html)
        self.assertLess(len(html.encode("utf-8")), 10_000_000)
        self.assertIn("OpenStreetMap contributors", html)
        notebook = json.loads(
            (ROOT / "istanbul_earthquake_analysis.ipynb").read_text(encoding="utf-8")
        )
        code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertTrue(all(c["execution_count"] is not None for c in code_cells))
        self.assertFalse(
            any(o["output_type"] == "error" for c in code_cells for o in c["outputs"])
        )

    def test_polygon_match_count_and_uniqueness(self):
        if not geo.NEIGHBOURHOOD_CACHE.exists():
            self.skipTest("Run the build first to download the boundary snapshot")
        polys = geo.load_neighbourhood_polygons()
        self.assertFalse(polys.key.duplicated().any())
        nb = geo.attach_polygons(self.df, polys)
        self.assertEqual(len(nb), 959)
        self.assertEqual(nb.geometry.notna().sum(), 953)
        self.assertEqual(
            set(nb.loc[nb.geometry.isna(), "neighbourhood"]),
            {
                "Fevzi Çakmak",
                "Hürriyet",
                "Kocasinan Merkez",
                "Evliya Çelebi",
                "İstiklal",
                "Gümüşyaka",
            },
        )


if __name__ == "__main__":
    unittest.main()
