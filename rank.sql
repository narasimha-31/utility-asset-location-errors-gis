-- sort by flood rank, then check, then size
DROP TABLE IF EXISTS ranked_errors;

CREATE TABLE ranked_errors AS
WITH flood AS (
    SELECT
        e.*,
        z.fld_zone AS flood_zone,
        z.zone_subty AS flood_subtype,
        CASE
            WHEN z.sfha_tf = 'T' THEN 1
            WHEN z.zone_subty ILIKE '0.2 PCT%' THEN 2
            ELSE 3
        END AS flood_rank,
        CASE e.check_name
            WHEN 'osm_hifld_disagreement' THEN 1
            WHEN 'support_not_on_line' THEN 2
            WHEN 'possible_mapping_gap' THEN 3
            WHEN 'voltage_disagreement' THEN 4
            WHEN 'bad_voltage' THEN 5
            WHEN 'inconsistent_operator' THEN 6
            WHEN 'missing_voltage' THEN 7
            WHEN 'missing_operator' THEN 8
            ELSE 9
        END AS check_order
    FROM errors e
    LEFT JOIN LATERAL (
        -- riskiest zone if they overlap
        SELECT fld_zone, zone_subty, sfha_tf
        FROM flood_zones z
        WHERE ST_Intersects(z.geom, e.geom)
        ORDER BY (sfha_tf = 'T') DESC, (zone_subty ILIKE '0.2 PCT%') DESC
        LIMIT 1
    ) z ON true
)
SELECT
    row_number() OVER (ORDER BY flood_rank, check_order, size_ft DESC NULLS LAST, error_id) AS priority,
    *
FROM flood;
