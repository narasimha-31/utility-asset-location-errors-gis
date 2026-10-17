# Architecture

This project checks public Houston power grid maps for location and data errors, then
ranks them by how much they would slow storm restoration. All data is real and public.

## Steps

1. **Sources.** OpenStreetMap has the poles, towers, lines and substations plus the
   critical sites (hospitals, fire and police stations, water plants). HIFLD is a federal
   map of transmission lines made separately from OSM. FEMA has the flood hazard zones.
2. **Fetch.** Python downloads each source and saves the raw files. Nothing is changed here.
3. **Load.** GeoPandas converts every layer to EPSG:2278 so all distances are in US feet,
   then writes the layers to PostGIS.
4. **Check and rank.** SQL in PostGIS runs five checks and writes every problem to an
   errors table. Each error then gets points for being in a flood zone, near a critical
   site, on a high voltage line, and for how large the error is.
5. **Outputs.** A ranked CSV report, a QGIS map, and a hand check of 30 errors against
   aerial imagery. The README only uses numbers from the actual run.

## The five checks

| Check | What it finds |
|-------|---------------|
| duplicates | two poles or towers within 3 ft of each other |
| orphans | a pole or tower that is not on any power line |
| line gaps | a line end that stops just short of another line or tower |
| missing info | lines with no voltage or operator |
| OSM vs HIFLD offset | an OSM transmission line far from the federal line for the same route |

## What each tool does

| Tool | Job |
|------|-----|
| Python + requests | downloads each source |
| GeoPandas | reads the files, converts them to US feet, writes them to PostGIS |
| PostgreSQL + PostGIS | stores the layers and runs the checks |
| pandas | builds the CSV report and summary numbers |
| QGIS | shows the errors on a map and is used for the hand check |
| Docker | runs PostGIS the same way on any machine |

## Why US feet

Latitude and longitude are angles, so distances measured in them are not real lengths.
EPSG:2278 is a flat grid made for this part of Texas, so a distance of 50 means 50 feet
on the ground.
