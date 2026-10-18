-- tolerances in US feet
SET LOCAL qa.location_ft = '100';
SET LOCAL qa.not_found_ft = '1000';
SET LOCAL qa.sample_step_ft = '100';

DROP TABLE IF EXISTS errors;
CREATE TABLE errors (
    error_id serial PRIMARY KEY,
    check_name text NOT NULL,
    feature_type text NOT NULL,
    feature_id text NOT NULL,
    detail text,
    size_ft numeric,
    geom geometry(Point, 2278)
);


-- hifld vs nearest osm line
WITH samples AS (
    SELECT h.id, (ST_DumpPoints(ST_Segmentize(h.geom, current_setting('qa.sample_step_ft')::numeric))).geom AS geom
    FROM hifld_lines h
    WHERE NOT h.from_osm
),
gaps AS (
    SELECT s.id, s.geom, coalesce(near.dist, 'Infinity'::float) AS dist
    FROM samples s
    LEFT JOIN LATERAL (
        SELECT ST_Distance(s.geom, o.geom) AS dist
        FROM osm_lines o
        WHERE o.power = 'line'
        ORDER BY s.geom <-> o.geom
        LIMIT 1
    ) near ON true
),
worst AS (
    SELECT DISTINCT ON (id) id, geom, dist
    FROM gaps
    ORDER BY id, dist DESC
)
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT
    'osm_hifld_disagreement',
    'hifld_line',
    id,
    CASE
        WHEN dist > current_setting('qa.not_found_ft')::numeric
            THEN 'line is in HIFLD but not found in OSM within ' || current_setting('qa.not_found_ft') || ' ft'
        ELSE 'OSM and HIFLD put this line ' || round(dist::numeric) || ' ft apart'
    END,
    CASE WHEN dist = 'Infinity'::float THEN NULL ELSE round(dist::numeric, 1) END,
    geom
FROM worst
WHERE dist > current_setting('qa.location_ft')::numeric;
