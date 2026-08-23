# QA — Precision Model v2

Release gate for the 100m population × OSM walking-network model.

## Required live-data checks

1. Matsuyama AED CSV downloads and has valid coordinates.
2. Matsuyama public-facility CSV downloads and has valid coordinates.
3. `100m_mesh_pop2020_38201.zip` downloads and contains `Meshcode`, `PopT`, `Pop75over`.
4. Tiled Overpass acquisition returns a non-trivial walking graph.
5. At least one all-AED and one 24h AED are snapped to the graph.
6. Positive-population 100m meshes exceed 1,000 and >90% of population is network-snapped.
7. Candidate facilities exist after 50m existing-AED exclusion.
8. Network distances, not Haversine distances, drive coverage and candidate gain.
9. All-AED coverage is not lower than 24h-only coverage at the same threshold.
10. UI JavaScript passes syntax validation.

## Model truthfulness

- Population: 2020 Census 250m population redistributed to simplified 100m cells; not actual 100m census tabulation.
- No 2026 small-area spatial rescaling.
- Walking network: OSM build-time snapshot via Overpass.
- Distance: mesh snap + shortest road/path distance + AED/candidate snap.
- `4 min`: 320m at 4.8 km/h, one-way analytical setting only.
- Unsnapped population stays in the denominator and is never silently dropped.
- Euclidean coverage circles are not rendered as network isochrones.
