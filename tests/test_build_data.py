import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from network import CoordinateIndex, WalkingGraph, haversine_m, mesh100m_center, multisource_distances

SPEC = importlib.util.spec_from_file_location("build_data", SCRIPTS / "build_data.py")
build_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules["build_data"] = build_data
SPEC.loader.exec_module(build_data)


class NetworkUnitTest(unittest.TestCase):
    def test_haversine_zero(self):
        self.assertAlmostEqual(haversine_m(33.84, 132.76, 33.84, 132.76), 0.0, places=7)

    def test_haversine_known_scale(self):
        d = haversine_m(33.84, 132.76, 33.841, 132.76)
        self.assertGreater(d, 105)
        self.assertLess(d, 117)

    def test_mesh100m_center(self):
        lat, lon = mesh100m_center("5032371234")
        self.assertTrue(20 < lat < 50)
        self.assertTrue(120 < lon < 150)

    def test_multisource_shortest_path(self):
        graph = WalkingGraph(
            adjacency={"a": [("b", 100.0)], "b": [("a", 100.0), ("c", 150.0)], "c": [("b", 150.0)]},
            coordinates={"a": (33.0, 132.0), "b": (33.001, 132.0), "c": (33.002, 132.0)},
            edge_count=4,
        )
        dist = multisource_distances(graph, [("a", 20.0)], cutoff_m=400)
        self.assertEqual(dist["a"], 20.0)
        self.assertEqual(dist["b"], 120.0)
        self.assertEqual(dist["c"], 270.0)

    def test_coordinate_index_respects_max_snap(self):
        idx = CoordinateIndex({"a": (33.84, 132.76)})
        node, distance = idx.nearest(33.8401, 132.76, max_search_m=100)
        self.assertEqual(node, "a")
        self.assertLess(distance, 20)
        node, _ = idx.nearest(34.0, 132.76, max_search_m=100)
        self.assertIsNone(node)


class RealPayloadContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "data" / "processed.json").read_text(encoding="utf-8"))

    def test_precision_model_is_active(self):
        self.assertEqual(self.payload["meta"]["distanceModel"], "osm-walking-shortest-path")
        self.assertIn("100m", self.payload["meta"]["populationModel"])
        self.assertNotIn("regionCount", self.payload["summary"])

    def test_mesh_population_is_not_public_facility_proxy(self):
        demand = self.payload["demand"]
        self.assertGreater(len(demand), 1000)
        self.assertTrue(all(len(str(d["meshcode"])) == 10 for d in demand[:100]))
        self.assertTrue(all("nearestAllM" in d and "nearest24hM" in d for d in demand[:100]))

    def test_population_and_age_totals_are_positive(self):
        summary = self.payload["summary"]
        self.assertGreater(summary["population"], 100000)
        self.assertGreater(summary["senior75"], 10000)
        self.assertAlmostEqual(sum(d["population"] for d in self.payload["demand"]), summary["population"], delta=1.0)
        self.assertAlmostEqual(sum(d["senior75"] for d in self.payload["demand"]), summary["senior75"], delta=1.0)

    def test_network_snap_quality(self):
        summary = self.payload["summary"]
        self.assertGreater(summary["networkNodeCount"], 1000)
        self.assertGreater(summary["networkDirectedEdgeCount"], 1000)
        self.assertLess(summary["unsnappedPopulation"] / summary["population"], 0.10)

    def test_24h_is_subset_and_snapped(self):
        summary = self.payload["summary"]
        self.assertGreater(summary["aed24hCount"], 0)
        self.assertLessEqual(summary["aed24hCount"], summary["aedCount"])
        self.assertGreater(summary["aed24hNetworkSnappedCount"], 0)
        self.assertLessEqual(summary["aed24hNetworkSnappedCount"], summary["aedNetworkSnappedCount"])

    def test_candidate_reach_uses_network_distances(self):
        self.assertGreater(self.payload["summary"]["candidateCount"], 0)
        max_radius = self.payload["meta"]["maxRadiusM"]
        for c in self.payload["candidates"][:50]:
            nearest = c["nearestAedNetworkM"] if c["nearestAedNetworkM"] is not None else max_radius + 1
            self.assertGreaterEqual(nearest, 50)
            self.assertTrue(c["reach"])
            self.assertTrue(all(0 <= pair[0] < len(self.payload["demand"]) and 0 <= pair[1] <= max_radius for pair in c["reach"]))


if __name__ == "__main__":
    unittest.main()
