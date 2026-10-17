# Architecture

This project checks public Houston power grid maps for location errors by comparing
independent sources that describe the same equipment. Where they disagree, at least
one of them is wrong. All data is real and public.

## Flow

```mermaid
flowchart TD
    subgraph S["1. Public sources"]
        OSM["OpenStreetMap<br/>poles, towers, lines,<br/>substations, hospitals,<br/>fire and police stations"]
        HIFLD["HIFLD<br/>federal transmission lines"]
        MLY["Mapillary<br/>poles detected in<br/>street photos"]
        FEMA["FEMA<br/>flood hazard zones"]
    end

    subgraph F["2. Fetch (Python, requests)"]
        RAW["data/raw<br/>GeoJSON files, not in git"]
    end

    subgraph L["3. Load (GeoPandas)"]
        PROJ["reproject to EPSG:2278<br/>NAD83 Texas South Central, US feet"]
    end

    subgraph DB["4. PostGIS in Docker"]
        T["source tables<br/>osm_poles, osm_towers, osm_lines,<br/>hifld_lines, mly_poles,<br/>flood_zones, critical_sites"]
        C["checks in SQL<br/>duplicates, orphans, line gaps,<br/>missing info, map disagreement,<br/>no photo evidence"]
        E["errors table"]
        R["ranked_errors<br/>flood + critical site +<br/>voltage + error size"]
    end

    subgraph O["5. Outputs"]
        CSV["output/error_report.csv"]
        QGIS["QGIS project<br/>reads PostGIS directly"]
        PNG["map image for README"]
        HC["hand check of 30 errors<br/>on aerial imagery"]
        MD["README<br/>real numbers from the run"]
    end

    OSM --> RAW
    HIFLD --> RAW
    MLY --> RAW
    FEMA --> RAW
    RAW --> PROJ --> T
    T --> C --> E --> R
    R --> CSV
    R --> QGIS --> PNG
    QGIS --> HC
    CSV --> MD
    HC --> MD
    PNG --> MD
```

## What each tool does

| Tool | Job |
|------|-----|
| Python + requests | downloads each source into data/raw |
| GeoPandas | reads the files, converts every layer to US feet, writes them to PostGIS |
| PostgreSQL + PostGIS | stores the layers and runs the distance and overlap checks |
| pandas | turns the ranked errors into the CSV report and summary numbers |
| QGIS | shows the errors on a map and is used to hand check a sample |
| Docker | runs PostGIS the same way on any machine |

## Why US feet

Lat and long are angles, so distances measured in them are not real lengths.
EPSG:2278 is a flat projection made for this part of Texas, so a distance of 50
means 50 feet on the ground. Every check uses it.
