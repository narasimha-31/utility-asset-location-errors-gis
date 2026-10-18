-- tolerances in US feet
SET LOCAL qa.location_ft = '100';
SET LOCAL qa.not_found_ft = '1000';
SET LOCAL qa.sample_step_ft = '100';
SET LOCAL qa.support_ft = '5';
SET LOCAL qa.touch_ft = '1';
SET LOCAL qa.substation_ft = '50';

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


-- supports not on a line
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT
    'support_not_on_line',
    s.power,
    s.osm_id::text,
    CASE
        WHEN near.dist IS NULL THEN 'no line anywhere in the data'
        ELSE 'nearest line is ' || round(near.dist::numeric) || ' ft away'
    END,
    round(near.dist::numeric, 1),
    s.geom
FROM osm_supports s
LEFT JOIN LATERAL (
    SELECT ST_Distance(s.geom, l.geom) AS dist
    FROM osm_lines l
    ORDER BY s.geom <-> l.geom
    LIMIT 1
) near ON true
WHERE near.dist IS NULL OR near.dist > current_setting('qa.support_ft')::numeric;


-- line groups with no substation, skip groups leaving the study area
WITH groups AS (
    SELECT osm_id, power, geom,
           ST_ClusterDBSCAN(geom, eps := current_setting('qa.touch_ft')::numeric, minpoints := 1) OVER () AS grp
    FROM osm_lines
),
reach AS (
    SELECT
        g.grp,
        count(*) AS lines,
        bool_or(EXISTS (
            SELECT 1 FROM osm_substations s
            WHERE ST_DWithin(g.geom, s.geom, current_setting('qa.substation_ft')::numeric)
        )) AS at_substation,
        bool_or(NOT ST_Within(g.geom, (SELECT geom FROM study_area LIMIT 1))) AS leaves_area
    FROM groups g
    GROUP BY g.grp
)
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT
    'possible_mapping_gap',
    g.power,
    g.osm_id::text,
    'part of a group of ' || r.lines || ' touching line(s) that never reaches a substation',
    round(ST_Length(g.geom)::numeric, 1),
    ST_LineInterpolatePoint(g.geom, 0.5)
FROM groups g
JOIN reach r USING (grp)
WHERE NOT r.at_substation AND NOT r.leaves_area;


-- missing voltage and operator
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT 'missing_voltage', power, osm_id::text, 'voltage is empty', NULL, ST_LineInterpolatePoint(geom, 0.5)
FROM osm_lines
WHERE coalesce(trim(voltage), '') = '';

INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT 'missing_operator', power, osm_id::text, 'operator is empty', NULL, ST_LineInterpolatePoint(geom, 0.5)
FROM osm_lines
WHERE coalesce(trim(operator), '') = '';


-- volts, circuits split by ;
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT 'bad_voltage', power, osm_id::text, 'voltage "' || voltage || '" is not plain numbers', NULL,
       ST_LineInterpolatePoint(geom, 0.5)
FROM osm_lines
WHERE coalesce(trim(voltage), '') <> ''
  AND voltage !~ '^[0-9]+(;[0-9]+)*$';


-- operator spelling variants
WITH spelled AS (
    SELECT osm_id, power, operator, geom,
           lower(regexp_replace(operator, '[^A-Za-z0-9]', '', 'g')) AS operator_key
    FROM osm_lines
    WHERE coalesce(trim(operator), '') <> ''
),
variants AS (
    SELECT operator_key, string_agg(DISTINCT operator, ' | ' ORDER BY operator) AS spellings
    FROM spelled
    GROUP BY operator_key
    HAVING count(DISTINCT operator) > 1
)
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT 'inconsistent_operator', s.power, s.osm_id::text, 'operator spelled more than one way: ' || v.spellings,
       NULL, ST_LineInterpolatePoint(s.geom, 0.5)
FROM spelled s
JOIN variants v USING (operator_key);


-- osm voltage vs hifld voltage (kV) on the same route
WITH osm AS (
    SELECT osm_id, power, voltage, geom, ST_LineInterpolatePoint(geom, 0.5) AS mid
    FROM osm_lines
    WHERE power = 'line' AND voltage ~ '^[0-9]+(;[0-9]+)*$'
),
matched AS (
    SELECT o.*, h.id AS hifld_id, h.voltage AS hifld_kv
    FROM osm o
    JOIN LATERAL (
        SELECT id, voltage
        FROM hifld_lines
        WHERE NOT from_osm
          AND voltage > 0
          AND ST_DWithin(o.mid, geom, current_setting('qa.location_ft')::numeric)
        ORDER BY o.mid <-> geom
        LIMIT 1
    ) h ON true
)
INSERT INTO errors (check_name, feature_type, feature_id, detail, size_ft, geom)
SELECT 'voltage_disagreement', power, osm_id::text,
       'OSM says ' || voltage || ' V, HIFLD line ' || hifld_id || ' says ' || hifld_kv || ' kV',
       NULL, mid
FROM matched
WHERE NOT (hifld_kv * 1000 = ANY (string_to_array(voltage, ';')::numeric[]));
