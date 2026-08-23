# Initial live-data validation

This file records the acceptance gate for the first GitHub-hosted PoC release.

The pull-request CI must execute the full pipeline against the official Matsuyama City open-data URLs and pass all of the following:

- download AED, 2026-04-01 regional/age population, and public-facility CSVs;
- fail on required-schema mismatch;
- model all 44 population regions;
- reconstruct total and 75+ population from demand-point weights within rounding tolerance;
- keep every placement candidate at least 50 m from an existing AED;
- confirm 24-hour-classified AEDs are a non-empty subset of all AEDs;
- calculate 300 m coverage and a non-negative best incremental placement for both all-AED and 24-hour-only modes;
- verify JavaScript syntax and deployable static-site files.

The analysis remains a PoC proxy model: regional population is distributed over public-facility anchors and coverage uses great-circle distance, not a pedestrian network isochrone.
