-- 1 = sfha zone, 2 = 0.2 pct zone, 3 = everything else, bigger gaps first
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
        END AS flood_rank
    FROM errors e
    LEFT JOIN LATERAL (
        -- riskiest zone wins where zones overlap
        SELECT fld_zone, zone_subty, sfha_tf
        FROM flood_zones z
        WHERE ST_Intersects(z.geom, e.geom)
        ORDER BY (sfha_tf = 'T') DESC, (zone_subty ILIKE '0.2 PCT%') DESC
        LIMIT 1
    ) z ON true
)
SELECT
    row_number() OVER (ORDER BY flood_rank, size_ft DESC NULLS LAST, error_id) AS priority,
    *
FROM flood;
