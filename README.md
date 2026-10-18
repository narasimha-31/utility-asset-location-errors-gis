# Utility Asset Location Errors in GIS Maps

Location errors are found by flagging where two independent sources disagree.

This project runs automated QA/QC on public power grid GIS data for central Houston and
ranks what it finds by flood risk, so the problems most likely to slow storm restoration
come first. It produces a ranked findings report and a visual QA map.

## Data

All data is real and public. No CenterPoint internal data is used, and nothing is
synthetic or simulated.

| Source | What | As of |
|--------|------|-------|
| OpenStreetMap (Overpass API) | poles, towers, power lines, substations | downloaded 17 Oct 2026 |
| HIFLD electric power transmission lines | reference layer for transmission lines | mapped 2017, validated 2017 to 2018 |
| FEMA National Flood Hazard Layer | flood hazard zones | downloaded 17 Oct 2026 |

Study area: latitude 29.65 to 29.85, longitude -95.50 to -95.25, about 15 by 14 miles
around downtown Houston. All distances are measured in EPSG:2278, NAD83 Texas South
Central, US feet.

Operator names such as "CenterPoint Energy" appear because volunteers tagged them in
OpenStreetMap and HIFLD lists the owner. They are public tags, not utility records.

What was loaded:

| Layer | Count |
|-------|-------|
| OSM poles | 1,777 |
| OSM towers | 1,650 |
| OSM transmission lines | 463 (273 miles) |
| OSM distribution lines | 88 (9 miles) |
| OSM substations | 63 |
| HIFLD lines in the study area | 148 (324 miles) |
| FEMA flood zone polygons | 1,209 |

Neither OSM nor HIFLD is treated as correct. 111 of the 148 HIFLD lines list
OpenStreetMap as a source, so they are copies and are not used for comparison. Only the
37 independent HIFLD lines are compared with OSM.

## Checks

| Group | Check | Flags | Tolerance |
|-------|-------|-------|-----------|
| location | disagreement between OSM and HIFLD | an independent HIFLD line whose furthest point is too far from any OSM transmission line | over 100 ft, sampled every 5 ft |
| connectivity | pole or tower not on a line | a support with no OSM line nearby | over 5 ft |
| connectivity | possible mapping gap | a group of touching lines that never reaches a substation | lines touch within 1 ft, substation within 50 ft |
| attributes | missing voltage, missing operator | an OSM line with the value empty | |
| attributes | bad voltage | voltage that is not whole numbers split by ";" | |
| attributes | inconsistent operator | one operator spelled more than one way | ignores case, spaces, punctuation |
| attributes | voltage disagreement | OSM line voltage that does not include the voltage of the independent HIFLD line on the same route | route match within 100 ft |

Line groups that run out of the study area are not flagged as gaps, because their far end
is not in the data.

## Ranking

| Flood rank | Where the finding is |
|------------|----------------------|
| 1 | FEMA high risk flood zone (A, AE, AO) |
| 2 | FEMA 0.2 percent annual chance zone |
| 3 | outside these zones |

Inside a rank, larger distances come first.

## Results

474 findings from the run on 17 to 18 Oct 2026.

| Check | Findings | Flood rank 1 | Flood rank 2 | Flood rank 3 |
|-------|----------|-------------|-------------|-------------|
| disagreement between OSM and HIFLD | 18 of 37 lines | 3 | 1 | 14 |
| pole or tower not on a line | 45 (35 poles, 10 towers) | 4 | 5 | 36 |
| possible mapping gap | 61 lines (13 transmission, 48 distribution) | 3 | 7 | 51 |
| voltage disagreement | 12 | 0 | 2 | 10 |
| missing voltage | 132 (45 transmission, 87 distribution) | 9 | 11 | 112 |
| missing operator | 206 (119 transmission, 87 distribution) | 17 | 23 | 166 |
| bad voltage | 0 | | | |
| inconsistent operator | 0 | | | |
| **total** | **474** | **36** | **49** | **389** |

Bad voltage and inconsistent operator ran and found nothing: every voltage in the data is
well formed and the operator is spelled one way.

### Top 10 by priority

All ten are in a FEMA AE flood zone.

| # | Check | Feature | Finding |
|---|-------|---------|---------|
| 1 | OSM vs HIFLD | HIFLD 301992 | in HIFLD, not found in OSM within 1,000 ft (6,400 ft at its worst point) |
| 2 | possible mapping gap | OSM way 312670853 | 4,127 ft distribution line that reaches no substation |
| 3 | OSM vs HIFLD | HIFLD 303822 | in HIFLD, not found in OSM within 1,000 ft (2,348 ft) |
| 4 | possible mapping gap | OSM way 1509655251 | 257 ft distribution line that reaches no substation |
| 5 | pole not on a line | OSM node 13768864962 | nearest line 251 ft away |
| 6 | pole not on a line | OSM node 13768864961 | nearest line 215 ft away |
| 7 | OSM vs HIFLD | HIFLD 300203 | the two sources put the line 199 ft apart |
| 8 | possible mapping gap | OSM way 1307620248 | 73 ft distribution line in a group of 2 that reaches no substation |
| 9 | pole not on a line | OSM node 13765423444 | nearest line 23 ft away |
| 10 | pole not on a line | OSM node 13768864960 | nearest line 18 ft away |

## How the results were checked

- **Unit tests.** 33 tests, written before the code. Each check is tested on small hand
  drawn shapes with a known answer, in a separate test database so the real results are
  never touched.
- **Independent recount.** A second script recomputes every check from the raw files with
  GeoPandas and Shapely, without the SQL, and compares the flagged features by ID. All
  eight checks flag exactly the same features. This recount found a real bug: sampling
  HIFLD every 100 ft missed one disagreement that fell between samples. Sampling every 5 ft
  fixed it, and the count went from 17 to 18.
- **Source counts.** Loaded counts match separate count only queries to OpenStreetMap,
  HIFLD and FEMA.
- **Imagery spot check.** The top seven findings were viewed over satellite imagery. They
  are real disagreements in the data, but at that resolution imagery cannot show which
  source is right. They are leads for field or engineering review, not confirmed errors.

## Limits

- HIFLD content is from 2017 to 2018. Lines rebuilt since then show up as disagreements
  even if OSM is right today.
- OSM has only 9 miles of distribution line here, so this is mostly a transmission check.
- Underground lines may be missing from one source, which looks like a disagreement or gap.
- In shared corridors a 69 kV and a 138 kV line can run within 100 ft of each other, so a
  voltage disagreement can come from matching two different lines.
- A possible mapping gap can be a line that really ends at a customer or plant, not a gap.

## How to run

Needs Docker, Python 3.12 and QGIS 3.44 LTR.

```
copy .env.example .env          then fill in the values, port 5433
docker compose up -d
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
python fetch.py                 downloads the three sources
python run.py                   loads, runs the checks, ranks, writes the report
python verify.py                independent recount of every finding
"C:\Program Files\QGIS 3.44.15\bin\python-qgis-ltr.bat" qgis\make_map.py
```

The QGIS project asks for the database password when opened. It is not stored in the file.

## Stack

Python (requests, pandas, GeoPandas, Shapely, SQLAlchemy), PostgreSQL 17 with PostGIS 3.5
in Docker, QGIS.
