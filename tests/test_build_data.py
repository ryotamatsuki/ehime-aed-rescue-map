import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_data", ROOT / "scripts" / "build_data.py")
build_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules["build_data"] = build_data
SPEC.loader.exec_module(build_data)


class BuildDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_data.build_payload(ROOT / "data" / "raw")

    def test_haversine_zero(self):
        self.assertAlmostEqual(build_data.haversine_m(33.84, 132.76, 33.84, 132.76), 0.0, places=7)

    def test_haversine_known_scale(self):
        d = build_data.haversine_m(33.84, 132.76, 33.841, 132.76)
        self.assertGreater(d, 105)
        self.assertLess(d, 117)

    def test_all_44_population_regions_are_modelled(self):
        self.assertEqual(self.payload["summary"]["regionCount"], 44)
        actual = {r["region"] for r in self.payload["regions"]}
        expected = {r["地域名"] for r in build_data.read_csv(ROOT / "data" / "raw" / build_data.POP_FILE)}
        self.assertEqual(actual, expected)

    def test_demand_weights_reconstruct_population(self):
        pop = sum(d["population"] for d in self.payload["demand"])
        senior = sum(d["senior75"] for d in self.payload["demand"])
        self.assertAlmostEqual(pop, self.payload["summary"]["population"], delta=1.0)
        self.assertAlmostEqual(senior, self.payload["summary"]["senior75"], delta=1.0)

    def test_candidates_are_not_on_top_of_existing_aed(self):
        aeds = self.payload["aeds"]
        for c in self.payload["candidates"]:
            nearest = min(build_data.haversine_m(c["lat"], c["lon"], a["lat"], a["lon"]) for a in aeds)
            self.assertGreaterEqual(nearest + 0.15, 50.0)

    def test_24h_is_subset(self):
        self.assertGreater(self.payload["summary"]["aed24hCount"], 0)
        self.assertLessEqual(self.payload["summary"]["aed24hCount"], self.payload["summary"]["aedCount"])


if __name__ == "__main__":
    unittest.main()
