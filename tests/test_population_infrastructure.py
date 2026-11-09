"""Checks for the population join, per-capita rates and infrastructure tables,
run with python -m unittest discover -s tests."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eqscenario import data, geo, index, infrastructure, modeling  # noqa: E402
from eqscenario import population as popn  # noqa: E402


def _toy() -> pd.DataFrame:
    """Three neighbourhoods in two districts with easy numbers."""
    return pd.DataFrame(
        {
            "district": ["A", "A", "B"],
            "neighbourhood": ["a1", "a2", "b1"],
            "population": [2000, 500, 10000],
            "buildings": [100, 50, 400],
            "deaths_serious": [10, 5, 20],
            "can_kaybi_sayisi": [6, 3, 12],
            "damage_index": [40.0, 10.0, 50.0],
            "damaged_buildings": [50, 10, 100],
            "cok_agir_hasarli_bina_sayisi": [5, 1, 4],
            "agir_hasarli_bina_sayisi": [5, 1, 6],
            "orta_hasarli_bina_sayisi": [10, 2, 30],
            "gecici_barinma": [100, 20, 300],
            "dogalgaz_boru_hasari": [0, 1, 2],
            "icme_suyu_boru_hasari": [0, 0, 3],
            "atik_su_boru_hasari": [1, 1, 4],
            "hastanede_tedavi_sayisi": [3, 1, 5],
            "hafif_yarali_sayisi": [6, 2, 9],
        }
    )


class PopulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = index.add_index(data.load_scenario())
        cls.pop = popn.load_population()

    def test_population_table(self):
        pop = self.pop
        self.assertEqual(sorted(pop.year.unique()), [2018, 2019, 2020])
        p19 = pop[pop.year == 2019]
        self.assertEqual(len(p19), 964)
        self.assertEqual(p19.population.sum(), 15_519_262)
        # The IMM district booklet for Adalar quotes 15,238 residents (TÜİK 2019).
        self.assertEqual(p19.loc[p19.district == "Adalar", "population"].sum(), 15_238)

    def test_every_scenario_row_gets_a_population(self):
        nb, unused = popn.attach_population(self.df, self.pop)
        self.assertEqual(len(nb), 959)
        self.assertTrue(nb.population.notna().all())
        self.assertEqual((nb.population_match == "uavt").sum(), 951)
        self.assertEqual((nb.population_match == "uavt code changed").sum(), 8)
        self.assertEqual(
            set(unused.neighbourhood),
            {"İkitelli Osb", "Beylikdüzüosb", "Dudullu Osb", "Finanskent", "Yenişehir"},
        )
        self.assertEqual(unused.population.sum(), 83 + 14 + 16 + 730 + 6444)
        self.assertEqual(
            nb.population.sum() + unused.population.sum(), 15_519_262
        )

    def test_changed_codes_point_to_the_same_names(self):
        p19 = self.pop[self.pop.year == 2019].set_index("uavt")
        rows = self.df.set_index("mahalle_koy_uavt")
        for old, new in popn.UAVT_CHANGES.items():
            self.assertNotIn(old, p19.index)
            self.assertEqual(geo._norm(rows.loc[old, "mahalle_adi"]), geo._norm(p19.loc[new, "neighbourhood"]))
            self.assertEqual(geo._norm(rows.loc[old, "ilce_adi"]), geo._norm(p19.loc[new, "district"]))

    def test_buildings_join_and_stock_bounds(self):
        nb = popn.attach_buildings(self.df, popn.load_buildings())
        self.assertEqual(len(nb), 959)
        self.assertTrue(nb.buildings.notna().all())
        self.assertTrue((nb.damaged_buildings <= nb.buildings).all())
        self.assertEqual(nb.buildings.sum(), 1_165_936)

    def test_per_capita_rates_and_threshold(self):
        out = popn.add_rates(_toy(), min_population=1000)
        np.testing.assert_allclose(out.casualties_per_1000, [5.0, 10.0, 2.0])
        np.testing.assert_allclose(out.deaths_per_1000, [3.0, 6.0, 1.2])
        np.testing.assert_allclose(out.damage_index_per_1000, [20.0, 20.0, 5.0])
        np.testing.assert_allclose(out.shelter_share_est, [0.15, 0.12, 0.09])
        np.testing.assert_allclose(out.damaged_share, [0.5, 0.2, 0.25])
        np.testing.assert_allclose(out.heavy_or_worse_share, [0.1, 0.04, 0.025])
        self.assertEqual(out.eligible.tolist(), [True, False, True])
        # The highest rate (a2) is below the threshold and gets no rank.
        self.assertEqual(out.rank_casualties_per_1000.tolist(), [1, pd.NA, 2])

    def test_zero_population_gives_missing_rate(self):
        toy = _toy()
        toy.loc[0, "population"] = 0
        out = popn.add_rates(toy)
        self.assertTrue(np.isnan(out.loc[0, "casualties_per_1000"]))
        self.assertFalse(out.loc[0, "eligible"])

    def test_district_rates_sum_before_dividing(self):
        d = popn.district_rates(popn.add_rates(_toy())).set_index("district")
        # (10 + 5) / (2000 + 500), not the mean of the two neighbourhood rates.
        self.assertAlmostEqual(d.loc["A", "casualties_per_1000"], 6.0)
        self.assertAlmostEqual(d.loc["B", "damaged_share"], 0.25)

    def test_identical_rankings_compare_perfectly(self):
        toy = popn.add_rates(_toy(), min_population=0)
        toy["deaths_serious"] = toy["casualties_per_1000"]
        cmp = popn.compare_rankings(
            toy, {"same": ("deaths_serious", "casualties_per_1000")}, top_ns=(2,)
        )
        self.assertAlmostEqual(cmp.loc[0, "spearman_absolute_vs_per_capita"], 1.0)
        self.assertEqual(cmp.loc[0, "top2_overlap"], 1.0)

    def test_offset_glm_recovers_a_rate_model(self):
        rng = np.random.default_rng(0)
        n = 2000
        x = rng.integers(0, 200, size=(n, 4)).astype(float)
        exposure = rng.integers(500, 50_000, size=n).astype(float)
        rate = np.exp(-8 + 0.5 * np.log1p(x[:, 0]))
        y = rng.poisson(rate * exposure)
        X = np.column_stack([x, exposure])
        pred = modeling.ExposurePoissonGLM().fit(X, y).predict(X)
        np.testing.assert_allclose(pred.sum(), y.sum(), rtol=0.02)
        self.assertGreater(np.corrcoef(pred, rate * exposure)[0, 1], 0.99)


class InfrastructureTests(unittest.TestCase):
    def test_utility_index_scaling(self):
        out = infrastructure.add_utility_index(_toy())
        # Each utility is scaled by its own mean, so the index averages to 1.
        self.assertAlmostEqual(out.utility_index.mean(), 1.0)
        ratios = _toy()[infrastructure.UTILITY_COLS] / _toy()[infrastructure.UTILITY_COLS].mean()
        np.testing.assert_allclose(out.utility_index, ratios.mean(axis=1))
        zero = _toy()
        zero.loc[0, infrastructure.UTILITY_COLS] = 0
        self.assertEqual(infrastructure.add_utility_index(zero).loc[0, "utility_index"], 0)

    def test_district_totals_conserve_city_totals(self):
        toy = infrastructure.add_utility_index(_toy())
        d = infrastructure.district_totals(toy)
        for col in infrastructure.UTILITY_COLS + ["gecici_barinma", "population"]:
            self.assertEqual(d[col].sum(), toy[col].sum())
        self.assertEqual(d.set_index("district").loc["A", "neighbourhoods"], 2)

    def test_source_columns_are_integer_counts(self):
        df = index.add_index(data.load_scenario())
        desc = infrastructure.describe_columns(df).set_index("column")
        self.assertTrue(desc.all_integer.all())
        self.assertEqual(desc.loc["dogalgaz_boru_hasari", "city_total"], 356)
        self.assertEqual(desc.loc["icme_suyu_boru_hasari", "city_total"], 461)
        self.assertEqual(desc.loc["atik_su_boru_hasari", "city_total"], 1042)
        self.assertEqual(desc.loc["gecici_barinma", "city_total"], 835_918)
        counts = infrastructure.value_counts_table(df)
        self.assertEqual(counts["natural gas"].sum(), 959)
        self.assertEqual(
            (counts["repair_points"] * counts["wastewater"]).sum(), 1042
        )

    def test_correlation_table_shape(self):
        df = infrastructure.add_utility_index(index.add_index(data.load_scenario()))
        corr = infrastructure.correlations(df)
        self.assertTrue(corr[["spearman", "pearson_log1p"]].abs().le(1).all().all())
        self.assertTrue((corr.n == 959).all())


class CommittedOutputTests(unittest.TestCase):
    def test_figures_are_small_and_map_has_new_layers(self):
        for png in (ROOT / "figures").glob("*.png"):
            self.assertLess(png.stat().st_size, 500_000, png.name)
        html = (ROOT / "maps" / "istanbul_damage_map.html").read_text(encoding="utf-8")
        for name in [
            "Deaths + serious injuries per 1,000 residents",
            "Pipe damage (combined index)",
            "Temporary shelter need (households)",
        ]:
            self.assertIn(name, html)
        self.assertNotIn("NaN", html)


if __name__ == "__main__":
    unittest.main()
